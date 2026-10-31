"""
psutil System Monitor — Project 6 (container edition)
Exposes real-time system metrics as Prometheus metrics using the cross-platform
`psutil` library instead of reading kernel files by hand.

Where this comes from:
  The native track's Project 6 ("Mac System Monitor") runs this exact psutil
  code directly on macOS. A container can never see the macOS host — Docker
  Desktop runs containers inside a small Linux VM — so the containerized
  version reports on the Linux host that Docker runs on (WSL2 / Linux / the
  Docker Desktop VM). The collector code is unchanged; that is the lesson:
  psutil hides the OS differences, Project 4 parses /proc by hand.

Container specifics:
  PROCFS_PATH=/host/proc  → psutil reads the HOST's /proc (bind-mounted
                            read-only by docker-compose.yml) for CPU, memory,
                            disk I/O and uptime.
  Network counters        → /proc/net is per network namespace, so these show
                            the CONTAINER's own interfaces (eth0, lo), not the
                            host's. Node Exporter has the same limit and is run
                            with network_mode: host when host NICs are needed.
  Disk usage              → psutil.disk_partitions() inside a container lists
                            Docker's bind-mounted files (/etc/hosts, ...). Set
                            DISK_PATHS (comma-separated) to report specific
                            paths instead; compose sets DISK_PATHS=/ — the
                            container root, which lives on Docker's data disk.
  Battery                 → read from /sys/class/power_supply. Present on a
                            laptop running WSL2; empty on servers and most VMs.

Metrics produced:
  host_cpu_usage_percent           Gauge   — overall CPU usage 0-100
  host_cpu_core_usage_percent      Gauge   — per-core usage, label: core
  host_memory_total_bytes          Gauge   — total physical RAM
  host_memory_used_bytes           Gauge   — RAM in use
  host_memory_usage_percent        Gauge   — used RAM as a percentage
  host_swap_total_bytes            Gauge   — total swap space
  host_swap_used_bytes             Gauge   — swap currently in use
  host_load_average                Gauge   — 1m/5m/15m load, label: interval
  host_disk_usage_percent          Gauge   — filesystem used %, label: mount
  host_disk_read_bytes_total       Gauge   — cumulative bytes read since boot
  host_disk_write_bytes_total      Gauge   — cumulative bytes written since boot
  host_net_bytes_sent_total        Gauge   — cumulative bytes sent, label: nic
  host_net_bytes_recv_total        Gauge   — cumulative bytes received, label: nic
  host_battery_percent             Gauge   — battery charge 0-100 (laptops only)
  host_battery_plugged             Gauge   — 1 if on AC power, 0 if on battery
  host_uptime_seconds              Gauge   — seconds since last boot

Routes:
  GET /          → health check
  GET /snapshot  → current readings as JSON (useful for debugging)
  GET /metrics   → Prometheus scrapes this
"""

import os
import threading
import time

import psutil
from flask import Flask, jsonify
from prometheus_client import Gauge, generate_latest, CONTENT_TYPE_LATEST

app = Flask(__name__)

# Point psutil at the host's /proc instead of the container's own.
# (Unset when run directly on a host — psutil then uses /proc as usual.)
if os.environ.get("PROCFS_PATH"):
    psutil.PROCFS_PATH = os.environ["PROCFS_PATH"]

# A label so the same dashboard can tell hosts apart if several are scraped.
HOST_OS = os.environ.get("HOST_OS", "linux")

# Optional fixed list of paths for disk usage (e.g. "/,/data"). Empty → every
# physical partition psutil finds, which is the right choice outside a container.
DISK_PATHS = [p.strip() for p in os.environ.get("DISK_PATHS", "").split(",") if p.strip()]
PORT = 8086

# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------

CPU_USAGE = Gauge("host_cpu_usage_percent", "Overall CPU usage percentage (0-100)")
CPU_CORE_USAGE = Gauge(
    "host_cpu_core_usage_percent", "Per-core CPU usage percentage (0-100)", ["core"]
)

MEM_TOTAL = Gauge("host_memory_total_bytes", "Total physical memory installed, in bytes")
MEM_USED = Gauge("host_memory_used_bytes", "Physical memory in use, in bytes")
MEM_USAGE_PCT = Gauge("host_memory_usage_percent", "Percentage of memory in use (0-100)")

SWAP_TOTAL = Gauge("host_swap_total_bytes", "Total swap space in bytes")
SWAP_USED = Gauge("host_swap_used_bytes", "Swap space currently in use, in bytes")

LOAD_AVG = Gauge("host_load_average", "System load average", ["interval"])

DISK_USAGE_PCT = Gauge(
    "host_disk_usage_percent", "Filesystem space used as a percentage", ["mount"]
)
DISK_READ = Gauge(
    "host_disk_read_bytes_total", "Cumulative bytes read from disk since boot"
)
DISK_WRITE = Gauge(
    "host_disk_write_bytes_total", "Cumulative bytes written to disk since boot"
)

NET_SENT = Gauge(
    "host_net_bytes_sent_total", "Cumulative bytes sent since boot", ["nic"]
)
NET_RECV = Gauge(
    "host_net_bytes_recv_total", "Cumulative bytes received since boot", ["nic"]
)

BATTERY_PCT = Gauge("host_battery_percent", "Battery charge percentage (laptops only)")
BATTERY_PLUGGED = Gauge("host_battery_plugged", "1 if on AC power, 0 if on battery")

UPTIME = Gauge("host_uptime_seconds", "Seconds elapsed since the system last booted")

# Info-style label so queries can filter / display the OS.
HOST_INFO = Gauge("host_info", "Static host info (always 1)", ["os"])
HOST_INFO.labels(os=HOST_OS).set(1)

# ---------------------------------------------------------------------------
# Collector thread — updates all gauges every 5 seconds
# ---------------------------------------------------------------------------

_snapshot: dict = {}


def _collect():
    global _snapshot

    # First call to cpu_percent() returns 0.0 and primes the internal counters;
    # discard it so the first real reading (below) is meaningful.
    psutil.cpu_percent(interval=None)
    psutil.cpu_percent(interval=None, percpu=True)

    while True:
        try:
            # --- CPU ---
            overall = psutil.cpu_percent(interval=None)
            per_core = psutil.cpu_percent(interval=None, percpu=True)
            CPU_USAGE.set(overall)
            for i, pct in enumerate(per_core):
                CPU_CORE_USAGE.labels(core=f"cpu{i}").set(pct)

            # --- Memory ---
            vm = psutil.virtual_memory()
            MEM_TOTAL.set(vm.total)
            MEM_USED.set(vm.used)
            MEM_USAGE_PCT.set(vm.percent)

            sm = psutil.swap_memory()
            SWAP_TOTAL.set(sm.total)
            SWAP_USED.set(sm.used)

            # --- Load average (available on macOS and Linux) ---
            load1, load5, load15 = psutil.getloadavg()
            LOAD_AVG.labels(interval="1m").set(load1)
            LOAD_AVG.labels(interval="5m").set(load5)
            LOAD_AVG.labels(interval="15m").set(load15)

            # --- Disk usage per mounted filesystem ---
            mounts = DISK_PATHS or [p.mountpoint for p in psutil.disk_partitions(all=False)]
            for mount in mounts:
                try:
                    usage = psutil.disk_usage(mount)
                    DISK_USAGE_PCT.labels(mount=mount).set(usage.percent)
                except (PermissionError, OSError):
                    continue

            # --- Disk I/O (system-wide totals since boot) ---
            dio = psutil.disk_io_counters()
            if dio:
                DISK_READ.set(dio.read_bytes)
                DISK_WRITE.set(dio.write_bytes)

            # --- Network I/O per interface ---
            for nic, counters in psutil.net_io_counters(pernic=True).items():
                NET_SENT.labels(nic=nic).set(counters.bytes_sent)
                NET_RECV.labels(nic=nic).set(counters.bytes_recv)

            # --- Battery (None on desktops / VMs / containers) ---
            battery = psutil.sensors_battery()
            if battery is not None:
                BATTERY_PCT.set(battery.percent)
                BATTERY_PLUGGED.set(1 if battery.power_plugged else 0)

            # --- Uptime ---
            uptime = time.time() - psutil.boot_time()
            UPTIME.set(uptime)

            # Snapshot for the /snapshot endpoint
            _snapshot = {
                "os": HOST_OS,
                "cpu_usage_percent": round(overall, 2),
                "memory_total_gb": round(vm.total / 1e9, 2),
                "memory_used_gb": round(vm.used / 1e9, 2),
                "memory_usage_percent": round(vm.percent, 2),
                "load_average": {"1m": load1, "5m": load5, "15m": load15},
                "battery_percent": round(battery.percent, 1) if battery else None,
                "procfs_path": psutil.PROCFS_PATH,
                "uptime_seconds": round(uptime),
            }

        except Exception as e:  # noqa: BLE001 — keep the collector alive
            print(f"[collector] error: {e}")

        time.sleep(5)


threading.Thread(target=_collect, daemon=True).start()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return jsonify({"service": "psutil-system-monitor", "status": "ok"})


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
    print(f"psutil System Monitor running on http://0.0.0.0:{PORT}")
    print(f"Snapshot: http://0.0.0.0:{PORT}/snapshot")
    print(f"Metrics:  http://0.0.0.0:{PORT}/metrics")
    app.run(host="0.0.0.0", port=PORT, debug=False)
