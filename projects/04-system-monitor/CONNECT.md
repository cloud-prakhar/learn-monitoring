# Connecting the System Monitor to Prometheus and Grafana

Follow these steps in order. Each one has a check so you know it worked before moving on.

---

## Before you start

The shared infrastructure must be running:

```bash
cd infra
docker compose up -d
docker network ls | grep monitoring
```

Expected:

```
xxxxxxxx   monitoring   bridge    local
```

---

## Step 1 — Start the System Monitor

From `projects/04-system-monitor/`:

```bash
docker compose up -d --build
```

Expected (last lines):

```
 ✔ Container system-monitor  Started
```

**Check the app answers and is reading the host's `/proc`:**

```bash
curl http://localhost:8084/
```

```json
{"proc_root":"/host/proc","service":"system-monitor","status":"ok"}
```

```bash
curl http://localhost:8084/snapshot
```

```json
{"cpu_usage_percent":0.58,"load_average":{"15m":0.11,"1m":0.21,"5m":0.2},"memory_available_gb":11.06,"memory_total_gb":12.35,"memory_usage_percent":10.46,"uptime_seconds":7147}
```

`memory_total_gb` should match the host — compare with `free -g` on Linux/WSL2. If it matches,
the bind mount works.

> The first `/snapshot` may be `{}` — the collector needs two `/proc/stat` reads, 5 seconds apart,
> to compute CPU usage. Wait a few seconds and retry.

---

## Step 2 — Add the scrape job to Prometheus

Open `infra/prometheus.yml` and uncomment the Project 4 block:

```yaml
# Before:
  # - job_name: "system-monitor"
  #   static_configs:
  #     - targets: ["system-monitor:8084"]

# After:
  - job_name: "system-monitor"
    static_configs:
      - targets: ["system-monitor:8084"]
```

The target is the **container name**, not `localhost` — Prometheus runs in its own container,
where `localhost` means Prometheus itself.

Check the file before reloading — a typo here is the most common failure:

```bash
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml
```

```
 SUCCESS: /etc/prometheus/prometheus.yml is valid prometheus config file syntax
```

---

## Step 3 — Reload Prometheus

```bash
curl -X POST http://localhost:9090/-/reload
```

Expected: an empty HTTP 200 response.

> The new target shows up on the Targets page within a few seconds, as **UNKNOWN** until its
> first scrape (up to 15 seconds). If it never appears, confirm Prometheus sees your edit:
> `docker exec prometheus grep -n '"system-monitor"' /etc/prometheus/prometheus.yml` must show
> the line without `#` — see `docs/troubleshooting.md` section 19.

---

## Step 4 — Validate connectivity, hop by hop

Wait ~15 seconds after the reload so the first scrape has happened. Each hop can fail on its
own, so check them in the order data flows.

**4a. The container is on the `monitoring` network:**

```bash
docker inspect system-monitor --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
```

Expected: `monitoring`

**4b. Prometheus can reach the app by name** (this is the exact request a scrape makes):

```bash
docker exec prometheus wget -qO- http://system-monitor:8084/metrics | grep ^system_memory_total
```

Expected: `system_memory_total_bytes 1.3256e+10` (your number will differ).

**4c. Prometheus reports the target UP:**

```bash
curl -s http://localhost:9090/api/v1/targets | grep -o '"job":"system-monitor"[^}]*' | head -1
curl -s 'http://localhost:9090/api/v1/query?query=up%7Bjob%3D%22system-monitor%22%7D'
```

The second command should contain `"value":[<timestamp>,"1"]`. Or open
**http://localhost:9090/targets** — `system-monitor (1/1 up)`.

**4d. Grafana can reach Prometheus** (the data source health check):

```bash
DS_UID=$(curl -s -u admin:admin http://localhost:3000/api/datasources/name/Prometheus \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["uid"])')
curl -s -u admin:admin http://localhost:3000/api/datasources/uid/$DS_UID/health
```

```json
{"message":"Successfully queried the Prometheus API.","status":"OK"}
```

**4e. Grafana can see this job's data:**

```bash
curl -s -u admin:admin \
  "http://localhost:3000/api/datasources/proxy/uid/$DS_UID/api/v1/query?query=system_cpu_usage_percent"
```

Expected: a `"result":[...]` with one series for `job="system-monitor"`.

**All of the above in one command** (run from the repo root):

```bash
scripts/validate-connectivity.sh system-monitor system-monitor:8084 system-monitor
```

```
== Validating job 'system-monitor'
-- Docker
  PASS  network 'monitoring' exists
  PASS  container 'prometheus' is running
  PASS  container 'grafana' is running
  PASS  container 'system-monitor' is running
  PASS  'system-monitor' is attached to 'monitoring'
  PASS  prometheus container can fetch http://system-monitor:8084/metrics
-- Prometheus
  PASS  all 1 target(s) for job 'system-monitor' are UP
  PASS  query up{job="system-monitor"} returns 1 series
-- Grafana
  PASS  Grafana API is up
  PASS  Grafana → Prometheus data source health is OK
  PASS  Grafana can query job 'system-monitor' through the data source (1 series)
  PASS  dashboard 'System Monitor' is loaded (http://localhost:3000/d/system-monitor)
== 12 passed, 0 failed
```

The first `FAIL` line tells you which hop is broken.

---

## Step 5 — Explore in Prometheus

Open **http://localhost:9090** and try:

| Query | What it shows |
|-------|--------------|
| `system_cpu_usage_percent{job="system-monitor"}` | Host CPU busy % |
| `system_cpu_core_usage_percent{job="system-monitor"}` | One line per core |
| `system_memory_total_bytes - system_memory_available_bytes` | Memory in use, bytes |
| `system_load_average{job="system-monitor"}` | 1m / 5m / 15m load |
| `rate(system_disk_write_bytes_total{job="system-monitor"}[1m])` | Disk write throughput, bytes/s |
| `system_uptime_seconds / 3600` | Host uptime in hours |

**Make the numbers move.** Burn one CPU core for 30 seconds from a throwaway container:

```bash
docker run --rm busybox timeout 30 sh -c 'while :; do :; done'
```

While it runs, query:

```promql
max(system_cpu_core_usage_percent{job="system-monitor"})
system_cpu_usage_percent{job="system-monitor"}
```

The busiest core climbs well above its idle level (typically 50–100% — the kernel moves the loop
between cores, so no single core may stay pinned). The overall figure rises by about
`100 / number-of-cores` percent: one busy core out of 16 adds ~6%. A container's CPU *is* the
host's CPU — that's why this monitor sees it.

---

## Step 6 — Open the Grafana dashboard

Open **http://localhost:3000** (login `admin` / `admin`).

**Option A — already provisioned:** Dashboards → Projects → **System Monitor**.
`infra/` loads it from `infra/grafana/dashboards/system-monitor.json`.

**Option B — import by hand** (if you run a Grafana without that provisioning):
Dashboards → New → Import → Upload `projects/04-system-monitor/dashboards/system-monitor.json`
→ pick the Prometheus data source → Import.

The dashboard has 8 panels: CPU, memory, 1m load and uptime stats on top; CPU over time
(overall + per core), memory total vs available, load averages, and disk I/O rate below.

---

## Metrics reference

| Metric name | Type | Labels |
|-------------|------|--------|
| `system_cpu_usage_percent` | Gauge | — |
| `system_cpu_core_usage_percent` | Gauge | core |
| `system_memory_total_bytes` / `_available_bytes` / `_usage_percent` | Gauge | — |
| `system_swap_total_bytes` / `_used_bytes` | Gauge | — |
| `system_load_average` | Gauge | interval |
| `system_disk_read_bytes_total` / `_write_bytes_total` | Gauge | device |
| `system_uptime_seconds` | Gauge | — |

```promql
# Swap in use as a percentage (0 if the host has no swap):
100 * system_swap_used_bytes / clamp_min(system_swap_total_bytes, 1)

# Load per core — above 1.0 means work is queuing:
system_load_average{interval="1m"} / scalar(count(system_cpu_core_usage_percent{job="system-monitor"}))
```

---

## Clean up

See **[CLEANUP.md](CLEANUP.md)**. Quick version: `docker compose down --rmi local`, then
re-comment the job in `infra/prometheus.yml` and reload Prometheus.
