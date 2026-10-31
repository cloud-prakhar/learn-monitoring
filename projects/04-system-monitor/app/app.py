"""
System Monitor — Project 4
Reads the Linux /proc filesystem to expose real-time system metrics.

Container edition: the app runs in a container on the shared `monitoring`
network. docker-compose.yml bind-mounts the HOST's /proc read-only at
/host/proc and sets PROC_ROOT=/host/proc, so every reading below comes from
the host kernel (on Docker Desktop that "host" is the Docker VM). This is the
same pattern Node Exporter uses with --path.procfs=/host/proc.

Metrics produced:
  system_cpu_usage_percent         Gauge   — overall CPU usage 0-100
  system_cpu_core_usage_percent    Gauge   — per-core usage, label: core
  system_memory_total_bytes        Gauge   — total physical RAM
  system_memory_available_bytes    Gauge   — available RAM (free + reclaimable)
  system_memory_usage_percent      Gauge   — used memory as a percentage
  system_swap_total_bytes          Gauge   — total swap space
  system_swap_used_bytes           Gauge   — used swap
  system_load_average              Gauge   — 1m/5m/15m load, label: interval
  system_disk_read_bytes_total     Gauge   — cumulative bytes read, label: device
  system_disk_write_bytes_total    Gauge   — cumulative bytes written, label: device
  system_uptime_seconds            Gauge   — seconds since last boot

Routes:
  GET /          → health check
  GET /snapshot  → current readings as JSON (useful for debugging)
  GET /metrics   → Prometheus scrapes this
"""

import os
import re
import threading
import time

from flask import Flask, jsonify
from prometheus_client import Gauge, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

# Where to read kernel files from. Default /proc works when run directly on a
# Linux host; the container sets PROC_ROOT=/host/proc (the host's /proc, mounted
# read-only by docker-compose.yml).
PROC_ROOT = os.environ.get("PROC_ROOT", "/proc").rstrip("/")


def _proc(name: str) -> str:
    """Return the full path of a /proc file under PROC_ROOT."""
    return f"{PROC_ROOT}/{name}"

# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------

CPU_USAGE = Gauge(
    "system_cpu_usage_percent",
    "Overall CPU usage percentage (0-100)",
)

CPU_CORE_USAGE = Gauge(
    "system_cpu_core_usage_percent",
    "Per-core CPU usage percentage (0-100)",
    ["core"],
)

MEM_TOTAL = Gauge(
    "system_memory_total_bytes",
    "Total physical memory installed, in bytes",
)

MEM_AVAILABLE = Gauge(
    "system_memory_available_bytes",
    "Memory available for new processes, in bytes (MemAvailable from /proc/meminfo)",
)

MEM_USAGE_PCT = Gauge(
    "system_memory_usage_percent",
    "Percentage of memory in use (0-100)",
)

SWAP_TOTAL = Gauge(
    "system_swap_total_bytes",
    "Total swap space in bytes",
)

SWAP_USED = Gauge(
    "system_swap_used_bytes",
    "Swap space currently in use, in bytes",
)

LOAD_AVG = Gauge(
    "system_load_average",
    "System load average",
    ["interval"],   # "1m", "5m", "15m"
)

DISK_READ = Gauge(
    "system_disk_read_bytes_total",
    "Cumulative bytes read from this block device since boot",
    ["device"],
)

DISK_WRITE = Gauge(
    "system_disk_write_bytes_total",
    "Cumulative bytes written to this block device since boot",
    ["device"],
)

UPTIME = Gauge(
    "system_uptime_seconds",
    "Seconds elapsed since the system last booted",
)

# ---------------------------------------------------------------------------
# /proc readers
# ---------------------------------------------------------------------------

_prev_cpu_stat: dict = {}


def _read_cpu_stat() -> dict:
    """Return {cpu_name: (idle_jiffies, total_jiffies)} from /proc/stat."""
    result = {}
    with open(_proc("stat")) as f:
        for line in f:
            if not line.startswith("cpu"):
                break
            parts = line.split()
            name = parts[0]
            # Fields: user nice system idle iowait irq softirq steal guest guest_nice
            vals = list(map(int, parts[1:11]))
            idle = vals[3] + vals[4]   # idle + iowait
            total = sum(vals)
            result[name] = (idle, total)
    return result


def _compute_cpu_usage() -> dict:
    """Return {cpu_name: usage_percent} by diffing two /proc/stat reads."""
    global _prev_cpu_stat
    current = _read_cpu_stat()
    if not _prev_cpu_stat:
        _prev_cpu_stat = current
        return {}
    usage = {}
    for name, (idle, total) in current.items():
        prev_idle, prev_total = _prev_cpu_stat.get(name, (idle, total))
        delta_total = total - prev_total
        delta_idle = idle - prev_idle
        usage[name] = (1.0 - delta_idle / delta_total) * 100.0 if delta_total > 0 else 0.0
    _prev_cpu_stat = current
    return usage


def _read_meminfo() -> dict:
    """Return {key: bytes} from /proc/meminfo. Values are converted from kB."""
    data = {}
    with open(_proc("meminfo")) as f:
        for line in f:
            key, val = line.split(":", 1)
            data[key.strip()] = int(val.strip().split()[0]) * 1024
    return data


def _read_loadavg() -> tuple:
    """Return (load1m, load5m, load15m) from /proc/loadavg."""
    with open(_proc("loadavg")) as f:
        parts = f.read().split()
    return float(parts[0]), float(parts[1]), float(parts[2])


def _read_diskstats() -> dict:
    """Return {device: (read_bytes, write_bytes)} for whole block devices only."""
    result = {}
    with open(_proc("diskstats")) as f:
        for line in f:
            parts = line.split()
            device = parts[2]
            # Match whole disks (sda, vda, nvme0n1) — skip partitions (sda1, nvme0n1p1).
            if re.match(r"^(sd[a-z]|vd[a-z]|nvme\d+n\d+|hd[a-z]|xvd[a-z])$", device):
                read_bytes = int(parts[5]) * 512    # sectors × 512 bytes
                write_bytes = int(parts[9]) * 512
                result[device] = (read_bytes, write_bytes)
    return result


def _read_uptime() -> float:
    """Return system uptime in seconds from /proc/uptime."""
    with open(_proc("uptime")) as f:
        return float(f.read().split()[0])

# ---------------------------------------------------------------------------
# Collector thread — updates all gauges every 5 seconds
# ---------------------------------------------------------------------------

_snapshot: dict = {}


def _collect():
    global _snapshot
    while True:
        try:
            # --- CPU ---
            cpu_usage = _compute_cpu_usage()
            if cpu_usage:
                CPU_USAGE.set(cpu_usage.get("cpu", 0.0))
                for name, pct in cpu_usage.items():
                    if name != "cpu":
                        CPU_CORE_USAGE.labels(core=name).set(pct)

            # --- Memory ---
            mem = _read_meminfo()
            total = mem.get("MemTotal", 0)
            avail = mem.get("MemAvailable", 0)
            MEM_TOTAL.set(total)
            MEM_AVAILABLE.set(avail)
            if total > 0:
                MEM_USAGE_PCT.set((1.0 - avail / total) * 100.0)
            swap_total = mem.get("SwapTotal", 0)
            swap_free = mem.get("SwapFree", 0)
            SWAP_TOTAL.set(swap_total)
            SWAP_USED.set(swap_total - swap_free)

            # --- Load average ---
            load1, load5, load15 = _read_loadavg()
            LOAD_AVG.labels(interval="1m").set(load1)
            LOAD_AVG.labels(interval="5m").set(load5)
            LOAD_AVG.labels(interval="15m").set(load15)

            # --- Disk ---
            for dev, (rb, wb) in _read_diskstats().items():
                DISK_READ.labels(device=dev).set(rb)
                DISK_WRITE.labels(device=dev).set(wb)

            # --- Uptime ---
            ut = _read_uptime()
            UPTIME.set(ut)

            # Snapshot for /snapshot endpoint
            _snapshot = {
                "cpu_usage_percent":    round(cpu_usage.get("cpu", 0.0), 2),
                "memory_total_gb":      round(total / 1e9, 2),
                "memory_available_gb":  round(avail / 1e9, 2),
                "memory_usage_percent": round((1.0 - avail / total) * 100.0, 2) if total else 0,
                "load_average":         {"1m": load1, "5m": load5, "15m": load15},
                "uptime_seconds":       round(ut),
            }

        except Exception as e:
            print(f"[collector] error: {e}")

        time.sleep(5)


threading.Thread(target=_collect, daemon=True).start()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return jsonify({"service": "system-monitor", "status": "ok", "proc_root": PROC_ROOT})


@app.route("/snapshot")
def snapshot():
    """Human-readable JSON dump of the latest collected values."""
    return jsonify(_snapshot)


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"System Monitor running on http://0.0.0.0:8084 (reading {PROC_ROOT})")
    print("Snapshot: http://0.0.0.0:8084/snapshot")
    print("Metrics:  http://0.0.0.0:8084/metrics")
    app.run(host="0.0.0.0", port=8084, debug=False)
