# Connecting Blackbox HTTP Probes to Prometheus and Grafana

Follow these steps in order. Each one has a check so you know it worked before moving on.

---

## Before you start

```bash
cd infra
docker compose up -d
docker network ls | grep monitoring
```

Start the projects you want probed. All targets pass when Projects 1–6 are running:

```bash
for p in 01-flask-web-api 02-job-processor 03-cache-service 04-system-monitor \
         05-url-health-checker 06-psutil-system-monitor; do
  (cd projects/$p && docker compose up -d --build)
done
```

Targets for projects you skip will show as failed probes — that is correct behaviour.

---

## Step 1 — Start the Blackbox Exporter

From `projects/07-blackbox-http-probes/`:

```bash
docker compose up -d
```

Expected:

```
 ✔ Container blackbox-http  Started
```

```bash
docker logs blackbox-http 2>&1 | grep -i "loaded config"
```

Expected: a line with `msg="Loaded config file"`. If instead you see `error parsing config file`,
fix `blackbox.yml` and run `docker compose restart blackbox-http`.

---

## Step 2 — Run probes by hand

Before Prometheus is involved, call the exporter yourself. This is the single most useful
debugging tool for probes.

```bash
curl -s 'http://localhost:9115/probe?module=http_2xx&target=http://flask-web-api:8081/' | grep -E '^probe_(success|http_status_code|duration)'
```

```
probe_duration_seconds 0.0042
probe_http_status_code 200
probe_success 1
```

Try the other modules:

```bash
# Body check — Grafana's health JSON must contain "database": "ok"
curl -s 'http://localhost:9115/probe?module=http_body_ok&target=http://grafana:3000/api/health' | grep ^probe_success

# POST, expecting 202 Accepted from Project 2
curl -s 'http://localhost:9115/probe?module=http_post_job&target=http://job-processor:8082/jobs' | grep -E '^probe_(success|http_status_code)'

# External HTTPS with TLS details (needs internet)
curl -s 'http://localhost:9115/probe?module=https_2xx_tls&target=https://prometheus.io' | grep -E '^probe_(success|ssl_earliest_cert_expiry|tls_version_info)'
```

**See a failure and why it failed** — add `&debug=true`:

```bash
curl -s 'http://localhost:9115/probe?module=http_body_ok&target=http://prometheus:9090/-/healthy&debug=true' | grep -iE 'regexp|succeeded|failed'
```

```
... msg="Body did not match regular expression" module=http_body_ok target=http://prometheus:9090/-/healthy regexp="\"(status|database)\": ?\"ok\""
... msg="Probe failed" module=http_body_ok target=http://prometheus:9090/-/healthy duration_seconds=0.0026
```

> These log lines appear because `docker-compose.yml` starts the exporter with
> `--log.prober=info`. Without that flag, probe logs stay at debug level and the
> `Logs for the probe:` section of `debug=true` output is empty.

Prometheus answers `Prometheus Server is Healthy.` — plain text, not JSON — so `http_body_ok`
is the wrong module for it. That is why it gets its own `http_prometheus_healthy` module.

The exporter's web page **http://localhost:9115** lists the most recent probes with these same
logs.

---

## Step 3 — Add the probe jobs to Prometheus

In `infra/prometheus.yml`, uncomment **both** Project 7 jobs: `blackbox-http` (the probes) and
`blackbox-exporter-http` (the exporter's own health). Remove the leading `# ` from every line of
the two blocks, keeping the indentation. They should look like this:

```yaml
  - job_name: "blackbox-http"
    metrics_path: /probe
    static_configs:
      - labels: {module: "http_2xx"}               # any 2xx = success
        targets:
          - http://flask-web-api:8081/
          ...
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [module]
        target_label: __param_module
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox-http:9115

  # The exporter's OWN health metrics (/metrics, not /probe).
  - job_name: "blackbox-exporter-http"
    static_configs:
      - targets: ["blackbox-http:9115"]
```

Check and reload:

```bash
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml
curl -X POST http://localhost:9090/-/reload
```

---

## Step 4 — Validate connectivity

**4a. Prometheus → exporter by name:**

```bash
docker exec prometheus wget -qO- http://blackbox-http:9115/metrics | grep '^blackbox_exporter_build_info'
```

**4b. Prometheus → exporter → target, the full probe path:**

```bash
docker exec prometheus wget -qO- \
  'http://blackbox-http:9115/probe?module=http_2xx&target=http://cache-service:8083/stats' | grep ^probe_success
```

Expected: `probe_success 1`.

> Wait ~15 seconds after the reload for the first scrape — before that, targets are UNKNOWN
> and the checks below report them as not UP.

**4c. Targets page.** Open **http://localhost:9090/targets** → `blackbox-http (13/13 up)`.
Each row's endpoint is `http://blackbox-http:9115/probe?module=…&target=…` — the relabeling at
work. "UP" here only means the exporter answered.

**4d. Everything at once, from the repo root:**

```bash
scripts/validate-connectivity.sh blackbox-http blackbox-http:9115 blackbox-http
scripts/validate-connectivity.sh blackbox-exporter-http blackbox-http:9115
```

```
== Validating job 'blackbox-http'
...
-- Prometheus
  PASS  all 13 target(s) for job 'blackbox-http' are UP
  PASS  query up{job="blackbox-http"} returns 13 series
  info  probe_success: 13/13 probes passing
-- Grafana
  PASS  Grafana → Prometheus data source health is OK
  PASS  Grafana can query job 'blackbox-http' through the data source (13 series)
  PASS  dashboard 'Blackbox HTTP Probes' is loaded (http://localhost:3000/d/blackbox-http)
== 12 passed, 0 failed
```

The `info probe_success` line lists any probe that is failing, by module and target. Without
internet access the two `https_2xx_tls` probes fail — expected.

---

## Step 5 — Explore in Prometheus

| Query | What it shows |
|-------|--------------|
| `probe_success{job="blackbox-http"}` | 1/0 per probe |
| `probe_success == 0` | Only the failing probes |
| `probe_http_status_code{job="blackbox-http"}` | Status code per target |
| `probe_duration_seconds{job="blackbox-http"}` | Total probe time |
| `sum by (phase) (probe_http_duration_seconds{instance="http://flask-web-api:8081/"})` | Where the time goes for one target |
| `(probe_ssl_earliest_cert_expiry - time()) / 86400` | Days until each certificate expires |
| `avg_over_time(probe_success{job="blackbox-http"}[1h]) * 100` | Availability % over the last hour |

---

## Step 6 — Break things and watch the probes react

**A crashed service:**

```bash
docker stop cache-service
```

Within one scrape (≤15s):

```bash
curl -s http://localhost:9090/api/v1/query --data-urlencode \
  'query=probe_success{instance="http://cache-service:8083/stats"}' | grep -o '"value":\[[^]]*\]'
```

Expected: `"value":[<timestamp>,"0"]`. Meanwhile `up{job="blackbox-http"}` is still 1 for that
row — the exporter is fine; the *target* is not. Bring it back:

```bash
docker start cache-service
```

**A flaky endpoint:** Project 1's `/error` fails ~40% of the time. Probe it by hand a few times:

```bash
for i in $(seq 1 6); do
  curl -s 'http://localhost:9115/probe?module=http_2xx&target=http://flask-web-api:8081/error' | grep ^probe_http_status_code
done
```

You'll see a mix of `200` and `500`. To graph it, add `- http://flask-web-api:8081/error` under
the `http_2xx` targets and reload — the state-timeline panel turns into a barcode.

---

## Step 7 — Open the Grafana dashboard

**http://localhost:3000** → Dashboards → Projects → **Blackbox HTTP Probes** (provisioned by
`infra/`). To import by hand: Dashboards → New → Import →
`projects/07-blackbox-http-probes/dashboards/blackbox-http.json`.

| Panel | Shows |
|---|---|
| Probes Passing / Failing | Count of `probe_success` 1 vs 0 |
| Slowest / Avg Probe Duration | Latency seen from outside |
| Soonest TLS Cert Expiry | Days until the first HTTPS certificate expires |
| Exporter Scrape | `up` of the exporter itself |
| Probe Result by Target | State timeline: green UP / red DOWN per module · target |
| Total Probe Duration by Target | `probe_duration_seconds` over time |
| HTTP Phases | Stacked resolve / connect / tls / processing / transfer |
| Current Status | Table: target, module, up, status code, duration |

---

## Clean up

See **[CLEANUP.md](CLEANUP.md)**.
