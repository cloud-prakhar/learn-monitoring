# Connecting the psutil System Monitor to Prometheus and Grafana

Follow these steps in order. Each one has a check so you know it worked before moving on.

---

## Before you start

```bash
cd infra
docker compose up -d
docker network ls | grep monitoring
```

Running Project 4 at the same time is recommended — Step 5 compares the two.

---

## Step 1 — Start the monitor

From `projects/06-psutil-system-monitor/`:

```bash
docker compose up -d --build
```

Expected:

```
 ✔ Container psutil-system-monitor  Started
```

**Check the readings:**

```bash
curl http://localhost:8086/snapshot
```

```json
{"battery_percent":69.4,"cpu_usage_percent":0.6,"load_average":{"15m":0.10,"1m":0.21,"5m":0.20},"memory_total_gb":12.35,"memory_usage_percent":10.5,"memory_used_gb":1.09,"os":"linux","procfs_path":"/host/proc","uptime_seconds":7149}
```

`"procfs_path": "/host/proc"` confirms psutil is reading the host's `/proc`. `battery_percent`
is `null` on machines without a battery.

**Check disk usage reports `/` only:**

```bash
curl -s http://localhost:8086/metrics | grep ^host_disk_usage
```

```
host_disk_usage_percent{mount="/"} 4.6
```

If you see `mount="/etc/hosts"` and friends instead, `DISK_PATHS` is missing from
`docker-compose.yml`.

---

## Step 2 — Add the scrape job to Prometheus

Uncomment the Project 6 block in `infra/prometheus.yml`:

```yaml
  - job_name: "psutil-system-monitor"
    static_configs:
      - targets: ["psutil-system-monitor:8086"]
```

```bash
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml
curl -X POST http://localhost:9090/-/reload
```

---

## Step 3 — Validate connectivity

**3a. On the network, and reachable from Prometheus by name:**

```bash
docker inspect psutil-system-monitor --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
docker exec prometheus wget -qO- http://psutil-system-monitor:8086/metrics | grep '^host_info'
```

Expected: `monitoring`, then `host_info{os="linux"} 1.0`.

> Wait ~15 seconds after the reload for the first scrape — before that, targets are UNKNOWN
> and the checks below report them as not UP.

**3b. Every hop through to Grafana, from the repo root:**

```bash
scripts/validate-connectivity.sh psutil-system-monitor psutil-system-monitor:8086 psutil-system-monitor
```

Expected: `== 12 passed, 0 failed`. Or open **http://localhost:9090/targets** —
`psutil-system-monitor (1/1 up)`.

---

## Step 4 — Explore in Prometheus

> Queries with `rate()` or `histogram_quantile()` need at least two scrapes inside their window,
> so they return nothing for the first ~30–60 seconds after the job is added. Plain gauges show
> up after one scrape.

| Query | What it shows |
|-------|--------------|
| `host_cpu_usage_percent{job="psutil-system-monitor"}` | Host CPU busy % |
| `host_memory_usage_percent` | RAM used % |
| `host_disk_usage_percent{mount="/"}` | Docker data disk used % |
| `rate(host_net_bytes_recv_total{nic="eth0"}[1m])` | Bytes/s into the container |
| `host_uptime_seconds / 3600` | Host uptime in hours |

**See the network counters move** — every Prometheus scrape is traffic into this container:

```bash
for i in $(seq 1 200); do curl -s http://localhost:8086/metrics > /dev/null; done
```

`rate(host_net_bytes_sent_total{nic="eth0"}[1m])` jumps.

---

## Step 5 — Compare with Project 4 (raw `/proc`)

With Project 4 running and scraped too, plot both side by side in Prometheus
(**Graph** tab):

```promql
system_cpu_usage_percent{job="system-monitor"}
host_cpu_usage_percent{job="psutil-system-monitor"}
```

They track each other — both read the same `/proc/stat`. Memory needs one thought:

```promql
system_memory_usage_percent{job="system-monitor"}     # (total - available) / total
host_memory_usage_percent{job="psutil-system-monitor"} # psutil's own formula
```

Both are based on `MemAvailable`, so they agree to within a fraction of a percent. Compare the
code: `_read_meminfo()` in Project 4 versus one `psutil.virtual_memory()` call here.

---

## Step 6 — Open the Grafana dashboard

**http://localhost:3000** → Dashboards → Projects → **psutil System Monitor** (provisioned by
`infra/`). To import by hand: Dashboards → New → Import →
`projects/06-psutil-system-monitor/dashboards/psutil-system-monitor.json`.

Panels: CPU, memory, 1m load and disk usage stats; CPU over time (overall + per core), memory
total vs used, container network throughput, disk I/O rate.

---

## Clean up

See **[CLEANUP.md](CLEANUP.md)**.
