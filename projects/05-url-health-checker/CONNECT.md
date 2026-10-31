# Connecting the URL Health Checker to Prometheus and Grafana

Follow these steps in order. Each one has a check so you know it worked before moving on.

---

## Before you start

```bash
cd infra
docker compose up -d
docker network ls | grep monitoring
```

The checker is more interesting with something to check — start any of Projects 1–4 and 6 you
like. Anything not running is reported as down.

---

## Step 1 — Start the checker

From `projects/05-url-health-checker/`:

```bash
docker compose up -d --build
```

Expected:

```
 ✔ Container url-health-checker  Started
```

**Check what it sees** (the first round runs right away):

```bash
curl -s http://localhost:8085/status | python3 -m json.tool | head -30
```

```json
{
    "details": {
        "http://cache-service:8083/stats": {
            "last_checked": "08:15:12",
            "response_ms": 6,
            "status_code": 200,
            "up": 1
        },
        ...
    },
    "down": 0,
    "total": 7,
    "up": 7
}
```

Following the recommended order (Projects 1–4 done, 6 not yet), expect `"up": 6, "down": 1` —
Project 6 (`psutil-system-monitor`) isn't running yet. A service you have not started shows
`"status_code": 0` and an error such as `Failed to resolve 'psutil-system-monitor'` — Docker DNS only knows names of **running** containers on
the network.

---

## Step 2 — Validate the checker's own connectivity

This project depends on connectivity in *both* directions: the checker must reach the other
containers, and Prometheus must reach the checker.

**2a. Checker → other containers by name** (`requests` is in the image, so use Python):

```bash
docker exec url-health-checker python -c \
  "import requests; print(requests.get('http://prometheus:9090/-/healthy', timeout=5).text)"
```

Expected: `Prometheus Server is Healthy.`

**2b. Prove `localhost` is the wrong address inside a container:**

```bash
docker exec url-health-checker python -c \
  "import requests; requests.get('http://localhost:9090/-/healthy', timeout=3)"
```

Expected: a `ConnectionError ... Connection refused` traceback. Nothing listens on 9090 *inside*
the checker container.

---

## Step 3 — Add the scrape job to Prometheus

Uncomment the Project 5 block in `infra/prometheus.yml`:

```yaml
  - job_name: "url-health-checker"
    static_configs:
      - targets: ["url-health-checker:8085"]
```

Check and reload:

```bash
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml
curl -X POST http://localhost:9090/-/reload
```

---

## Step 4 — Validate connectivity to Prometheus and Grafana

**4a. Prometheus → checker by name:**

```bash
docker exec prometheus wget -qO- http://url-health-checker:8085/metrics | grep '^url_up'
```

Expected: one `url_up{url="..."} 1.0` line per target.

> Wait ~15 seconds after the reload for the first scrape — before that, targets are UNKNOWN
> and the checks below report them as not UP.

**4b. Target UP, data queryable, Grafana connected — one command from the repo root:**

```bash
scripts/validate-connectivity.sh url-health-checker url-health-checker:8085 url-health-checker
```

Expected: `== 12 passed, 0 failed`. The checks are the same as Project 4's
[CONNECT.md](../04-system-monitor/CONNECT.md) Step 4, done in one go.

Or check by hand at **http://localhost:9090/targets** — `url-health-checker (1/1 up)`.

---

## Step 5 — Explore in Prometheus

> Queries with `rate()` or `histogram_quantile()` need at least two scrapes inside their window,
> so they return nothing for the first ~30–60 seconds after the job is added. Plain gauges show
> up after one scrape.

| Query | What it shows |
|-------|--------------|
| `url_up{job="url-health-checker"}` | 1/0 per URL |
| `count(url_up == 0)` | How many URLs are down right now |
| `url_status_code{job="url-health-checker"}` | Last status code per URL |
| `histogram_quantile(0.95, sum by (url, le) (rate(url_response_seconds_bucket[5m])))` | p95 response time per URL |
| `sum by (url) (rate(url_checks_total{result="error"}[5m]))` | Connection errors per second |

**Watch an outage happen.** Stop a monitored service, wait ~30 seconds, then start it again:

```bash
docker stop flask-web-api
curl -s http://localhost:8085/status | python3 -c \
  'import json,sys; d=json.load(sys.stdin)["details"]["http://flask-web-api:8081/"]; print(d["up"], d.get("error","")[:80])'
docker start flask-web-api
```

`url_up{url="http://flask-web-api:8081/"}` drops to 0 and comes back.

**Add a URL at runtime:**

```bash
curl -X POST http://localhost:8085/targets -H 'Content-Type: application/json' \
  -d '{"url": "http://blackbox-http:9115/"}'
```

(That is Project 7's exporter — `up=0` until you start it.)

---

## Step 6 — Open the Grafana dashboard

**http://localhost:3000** → Dashboards → Projects → **URL Health Checker** (provisioned by
`infra/`). To import by hand: Dashboards → New → Import →
`projects/05-url-health-checker/dashboards/url-health-checker.json`.

Panels: URLs monitored, URLs up, p50 response time, check error rate; up/down status over time,
p50 response time per URL, status codes, and errors per URL.

---

## Clean up

See **[CLEANUP.md](CLEANUP.md)**.
