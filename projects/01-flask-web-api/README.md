# Project 1 — Flask Web API

A small Python/Flask REST API that records Prometheus metrics on every HTTP request.
This is the simplest of the eight projects and the best one to start with.

---

## What it does

Exposes five routes and records how many requests each receives, how long they take,
and how many are in-flight at any moment.

```
GET /           → {"service": "flask-web-api", "status": "ok"}
GET /users      → list of 5 fake users
GET /users/<id> → single user, 404 if id > 100
GET /slow       → sleeps 300ms–1.2s  ← generates interesting latency data
GET /error      → returns HTTP 500 ~40% of the time  ← generates error-rate data
GET /metrics    → Prometheus scrapes this endpoint
```

---

## Metrics produced

| Metric | Type | What it measures |
|--------|------|-----------------|
| `http_requests_total` | Counter | Total requests by method, endpoint, status_code |
| `http_request_duration_seconds` | Histogram | Response time distribution |
| `active_requests` | Gauge | Requests currently being processed |

**Why each metric type was chosen:**
- **Counter** for request counts — a counter only goes up, which is perfect for tracking
  totals. You then use `rate()` in PromQL to turn the total into a per-second rate.
- **Histogram** for latency — a histogram tracks distribution across buckets, allowing
  you to compute percentiles (p50, p95, p99) with `histogram_quantile()`.
- **Gauge** for in-flight requests — a gauge can go up and down, which is correct for
  a value that represents "how many right now."

---

## Quick start

```bash
# 1. Start shared infra (if not already running)
cd infra && docker compose up -d && cd ..

# 2. Start this project
cd projects/01-flask-web-api
docker compose up -d --build

# 3. Test the app
curl http://localhost:8081/
curl http://localhost:8081/users
curl http://localhost:8081/slow

# 4. Connect to Prometheus + Grafana
# Follow CONNECT.md
```

---

## Files

| File | Purpose |
|------|---------|
| `app/app.py` | Flask application with metrics instrumentation |
| `app/requirements.txt` | Python dependencies (`flask`, `prometheus-client`) |
| `app/Dockerfile` | Container image definition |
| `docker-compose.yml` | Runs the app on the shared `monitoring` network |
| `CONNECT.md` | Step-by-step: wire to Prometheus, verify scraping, open dashboard |
| `dashboards/flask-web-api.json` | Importable Grafana dashboard for this project |

---

## Port

| Service | Port | URL |
|---------|------|-----|
| Flask Web API | 8081 | http://localhost:8081 |
| Metrics endpoint | 8081 | http://localhost:8081/metrics |
