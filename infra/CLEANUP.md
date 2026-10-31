# Clean Up — Shared Monitoring Infra

Tears down the shared Prometheus + Grafana stack started from `infra/`, including both data
volumes and the `monitoring` network that all projects connect to.

> **Stop the projects first.** Projects 01–08 attach to the `monitoring` network this stack
> creates. If any project container is still running, Docker will refuse to remove the network.
> Run each project's own `CLEANUP.md` before this one.

---

## Step 1 — Confirm no projects are still attached

```bash
docker ps --filter network=monitoring
```

Expected: only `prometheus` and `grafana` (or nothing). If you see any of `flask-web-api`,
`job-processor`, `cache-service`, `system-monitor`, `url-health-checker`,
`psutil-system-monitor`, `blackbox-http` or `blackbox-network`, stop those first with their
`CLEANUP.md` — or all at once from the repo root:

```bash
for p in projects/*/; do (cd "$p" && docker compose down --rmi local); done
```

---

## Step 2 — Tear down the stack

Run this from the `infra/` directory:

```bash
docker compose down -v
```

- `down` stops and removes the `prometheus` and `grafana` containers.
- `-v` removes the `promdata` and `grafdata` volumes (your metrics history and all Grafana
  dashboards/users). Omit `-v` if you want to keep dashboards for next time.
- Compose also removes the `monitoring` network it created.

---

## Step 3 — Restore prometheus.yml to its default

If you uncommented any project scrape jobs in `infra/prometheus.yml`, re-comment them so the next
person (or the next you) starts from the documented clean state. Each project's `CLEANUP.md`
covers removing its own job; this is just a reminder to double-check:

```bash
grep -n "job_name" infra/prometheus.yml
```

Expected: only `job_name: "prometheus"` should be uncommented.

---

## Optional — remove the images

```bash
docker rmi prom/prometheus:v3.12.0 grafana/grafana:13.0.1
docker rmi prom/blackbox-exporter:v0.27.0      # pulled by Projects 7 and 8
docker rmi python:3.12-slim                    # base image of Projects 1–6
```

---

## Verify it's clean

```bash
docker ps -a | grep -E "prometheus|grafana" || echo "no containers"
docker volume ls | grep -E "promdata|grafdata" || echo "no volumes"
docker network ls | grep monitoring || echo "no monitoring network"
```

Expected: all three lines report nothing left behind.
