"""
URL Health Checker — Project 5
Polls a list of URLs every 15 seconds and exposes availability and response
time as Prometheus metrics. Acts like a lightweight Blackbox Exporter.

Metrics produced:
  url_up                 Gauge     — 1 if last check returned 2xx/3xx, else 0, label: url
  url_status_code        Gauge     — last HTTP status code (0 = connection error), label: url
  url_response_seconds   Histogram — response time per URL, label: url
  url_checks_total       Counter   — total checks per URL, labels: url, result

Container edition: the checker runs on the shared `monitoring` network, so it
reaches the other services by CONTAINER NAME, not localhost. Inside a
container, "localhost" is the container itself — http://localhost:9090 would
find nothing.

Default monitored URLs (override with the TARGETS env var, comma-separated):
  http://prometheus:9090/-/healthy         — Prometheus health
  http://grafana:3000/api/health           — Grafana health
  http://flask-web-api:8081/               — Project 1 Flask Web API
  http://job-processor:8082/stats          — Project 2 Job Processor
  http://cache-service:8083/stats          — Project 3 Cache Service
  http://system-monitor:8084/              — Project 4 System Monitor
  http://psutil-system-monitor:8086/       — Project 6 psutil System Monitor

Poll interval: CHECK_INTERVAL_SECONDS env var (default 15).

Routes:
  GET    /         → health check
  GET    /targets  → list monitored URLs
  POST   /targets  → add URL  body: {"url": "http://..."}
  DELETE /targets  → remove URL  body: {"url": "http://..."}
  GET    /status   → current up/down status of all URLs
  GET    /metrics  → Prometheus scrapes this
"""

import os
import threading
import time

import requests as http_requests
from flask import Flask, jsonify, request
from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Target registry — thread-safe list of URLs to monitor
# ---------------------------------------------------------------------------

DEFAULT_TARGETS = [
    "http://prometheus:9090/-/healthy",
    "http://grafana:3000/api/health",
    "http://flask-web-api:8081/",
    "http://job-processor:8082/stats",
    "http://cache-service:8083/stats",
    "http://system-monitor:8084/",
    "http://psutil-system-monitor:8086/",
]

# TARGETS="http://a/,http://b/" replaces the default list (set in docker-compose.yml).
_env_targets = [u.strip() for u in os.environ.get("TARGETS", "").split(",") if u.strip()]
if _env_targets:
    DEFAULT_TARGETS = _env_targets

CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL_SECONDS", "15"))

_targets: list = list(DEFAULT_TARGETS)
_targets_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------

URL_UP = Gauge(
    "url_up",
    "1 if the URL returned HTTP 2xx/3xx on the last check, 0 if it failed",
    ["url"],
)

URL_STATUS_CODE = Gauge(
    "url_status_code",
    "Last HTTP status code returned (0 means a connection error or timeout)",
    ["url"],
)

URL_RESPONSE_TIME = Histogram(
    "url_response_seconds",
    "HTTP response time per URL in seconds",
    ["url"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

URL_CHECKS = Counter(
    "url_checks_total",
    "Total number of checks performed per URL",
    ["url", "result"],  # result = "success" | "error"
)

# ---------------------------------------------------------------------------
# Checker logic
# ---------------------------------------------------------------------------

_status_cache: dict = {}   # url → {up, status_code, response_ms, last_checked}


def _check_url(url: str) -> dict:
    try:
        start = time.time()
        resp = http_requests.get(url, timeout=5, allow_redirects=True)
        duration = time.time() - start
        up = 1 if resp.status_code < 400 else 0

        URL_UP.labels(url=url).set(up)
        URL_STATUS_CODE.labels(url=url).set(resp.status_code)
        URL_RESPONSE_TIME.labels(url=url).observe(duration)
        URL_CHECKS.labels(url=url, result="success").inc()

        return {
            "up": up,
            "status_code": resp.status_code,
            "response_ms": round(duration * 1000),
            "last_checked": time.strftime("%H:%M:%S"),
        }
    except Exception as exc:
        URL_UP.labels(url=url).set(0)
        URL_STATUS_CODE.labels(url=url).set(0)
        URL_CHECKS.labels(url=url, result="error").inc()
        return {
            "up": 0,
            "status_code": 0,
            "response_ms": None,
            "error": str(exc),
            "last_checked": time.strftime("%H:%M:%S"),
        }


def _poll_loop():
    """Background thread: check all targets in sequence, then sleep CHECK_INTERVAL s."""
    while True:
        with _targets_lock:
            current = list(_targets)
        for url in current:
            _status_cache[url] = _check_url(url)
        time.sleep(CHECK_INTERVAL)


threading.Thread(target=_poll_loop, daemon=True).start()

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return jsonify({"service": "url-health-checker", "status": "ok"})


@app.route("/targets", methods=["GET"])
def get_targets():
    with _targets_lock:
        return jsonify({"targets": list(_targets), "count": len(_targets)})


@app.route("/targets", methods=["POST"])
def add_target():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "url field is required"}), 400
    with _targets_lock:
        if url in _targets:
            return jsonify({"error": "url is already monitored"}), 409
        _targets.append(url)
    return jsonify({"added": url, "total_targets": len(_targets)}), 201


@app.route("/targets", methods=["DELETE"])
def remove_target():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    with _targets_lock:
        if url not in _targets:
            return jsonify({"error": "url not found"}), 404
        _targets.remove(url)
    _status_cache.pop(url, None)
    return jsonify({"removed": url, "total_targets": len(_targets)})


@app.route("/status")
def status():
    up_count = sum(1 for v in _status_cache.values() if v.get("up") == 1)
    return jsonify({
        "total": len(_status_cache),
        "up": up_count,
        "down": len(_status_cache) - up_count,
        "details": _status_cache,
    })


@app.route("/metrics")
def metrics():
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("URL Health Checker running on http://0.0.0.0:8085")
    print(f"Monitoring {len(_targets)} URLs every {CHECK_INTERVAL}s")
    print("Status:  http://0.0.0.0:8085/status")
    print("Metrics: http://0.0.0.0:8085/metrics")
    app.run(host="0.0.0.0", port=8085, debug=False)
