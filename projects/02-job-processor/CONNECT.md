# Connecting Job Processor to Prometheus and Grafana

---

## Before you start

Confirm the shared infrastructure is running:

```bash
docker network ls | grep monitoring
```

Expected output: a line showing `monitoring` with driver `bridge`.
If it is missing: `cd infra && docker compose up -d`

---

## Step 1 — Start the Job Processor

From the `projects/02-job-processor/` directory:

```bash
docker compose up -d --build
```

**Verify the app is up:**
```bash
curl http://localhost:8082/stats
```

Expected output:
```json
{"by_status": {}, "total_jobs": 0}
```

**Submit a test job to confirm it works:**
```bash
curl -X POST http://localhost:8082/jobs \
  -H "Content-Type: application/json" \
  -d '{"payload": "test-task"}'
```

Expected output:
```json
{"job_id": "a1b2c3d4", "status": "queued"}
```

**Check the raw metrics:**
```bash
curl http://localhost:8082/metrics | grep "^jobs_"
```

You should see counters and gauges for `jobs_submitted_total`, `job_queue_depth`, etc.

---

## Step 2 — Add the scrape job to Prometheus

Open `infra/prometheus.yml` and uncomment the `job-processor` block:

```yaml
# Before:
  # - job_name: "job-processor"
  #   static_configs:
  #     - targets: ["job-processor:8082"]

# After:
  - job_name: "job-processor"
    static_configs:
      - targets: ["job-processor:8082"]
```

---

## Step 3 — Reload Prometheus

Prometheus watches for a reload signal — you do not normally need to restart it:

```bash
curl -X POST http://localhost:9090/-/reload
```

Expected: HTTP 200 response (empty body). Confirm it picked up the file:

```bash
docker logs prometheus | tail -5
```

Look for:
```
msg="Completed loading of configuration file" filename=/etc/prometheus/prometheus.yml
```

> **If the new target never appears after a reload:** confirm Prometheus sees your edit —
> `docker exec prometheus grep -n job-processor /etc/prometheus/prometheus.yml` should show the
> line *without* `#`. `infra/` mounts its whole directory so editor saves always show through;
> if you changed it to a single-file mount, an editor that saves by "write temp file + rename"
> leaves Prometheus reading the old file. Restart forces a fresh mount:
>
> ```bash
> cd ../../infra && docker compose restart prometheus && cd -
> ```

---

## Step 4 — Verify the target is UP

Open **http://localhost:9090/targets**.

`job-processor (1/1 up)` should appear. If it shows DOWN:

```bash
# Is the container running at all?
docker ps | grep job-processor

# Is the container on the monitoring network?
docker inspect job-processor --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'

# Can Prometheus reach the metrics endpoint?
docker exec prometheus wget -qO- http://job-processor:8082/metrics | head -5
```

If the container is running and on the `monitoring` network but the target is still DOWN right
after editing the scrape config, re-read the inode note in Step 3 and restart Prometheus.

---

## Step 5 — Generate activity

The job processor does nothing on its own — you need to submit jobs.

**Submit a burst of 20 jobs:**
```bash
for i in $(seq 1 20); do
  curl -s -X POST http://localhost:8082/jobs \
    -H "Content-Type: application/json" \
    -d "{\"payload\": \"task-$i\"}" > /dev/null
done
echo "20 jobs submitted"
```

**Watch jobs being processed:**
```bash
# Check stats every 3 seconds:
watch -n 3 "curl -s http://localhost:8082/stats"
```

**Or run a continuous load loop (Ctrl+C to stop):**
```bash
while true; do
  curl -s -X POST http://localhost:8082/jobs \
    -H "Content-Type: application/json" \
    -d '{"payload": "continuous-task"}' > /dev/null
  sleep 2
done
```

---

## Step 6 — Explore in Prometheus

Open **http://localhost:9090** and try these queries:

| Query | What it shows |
|-------|--------------|
| `job_queue_depth{job="job-processor"}` | Jobs waiting right now |
| `jobs_currently_processing{job="job-processor"}` | Jobs being processed now |
| `rate(jobs_submitted_total{job="job-processor"}[1m])` | Submission rate (jobs/sec) |
| `rate(jobs_completed_total{job="job-processor"}[1m])` | Completion rate (jobs/sec) |
| `rate(jobs_failed_total{job="job-processor"}[1m]) / rate(jobs_submitted_total{job="job-processor"}[1m])` | Failure rate |
| `histogram_quantile(0.95, sum(rate(job_duration_seconds_bucket{job="job-processor"}[5m])) by (le))` | p95 processing time |

---

## Step 7 — Open the Grafana dashboard

**Option A — Combined overview:**
Dashboards → Projects → **All Projects Overview** → see the "Project 2 — Job Processor" row.

**Option B — Project-specific dashboard:**
Dashboards → New → Import → upload `projects/02-job-processor/dashboards/job-processor.json`

---

## Metrics reference

| Metric | Type | What it measures |
|--------|------|-----------------|
| `jobs_submitted_total` | Counter | Total jobs submitted via POST /jobs |
| `jobs_completed_total` | Counter | Jobs that finished without error |
| `jobs_failed_total` | Counter | Jobs that hit the 15% simulated failure |
| `job_duration_seconds` | Histogram | Processing time per job |
| `job_queue_depth` | Gauge | Jobs currently waiting (not yet picked up) |
| `jobs_currently_processing` | Gauge | Jobs being processed at this instant |

**Things to observe:**
- Queue depth rises when you submit faster than the worker processes
- The 15% failure rate produces a visible spike in `jobs_failed_total`
- Processing time is 0.5–5s, so the histogram shows a wide distribution
- When you stop submitting, queue depth drains to 0

---

## Clean up

> For a complete teardown (image, scrape job, and dashboard too), see **[CLEANUP.md](CLEANUP.md)**.
> Quick version:

```bash
docker compose down
```
