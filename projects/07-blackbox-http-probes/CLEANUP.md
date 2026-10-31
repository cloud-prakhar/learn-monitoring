# Clean Up — Blackbox HTTP Probes (Project 7)

Reverses [CONNECT.md](CONNECT.md). The shared `infra/` stack and the probed projects keep running.

---

## Step 1 — Stop and remove the exporter

From `projects/07-blackbox-http-probes/`:

```bash
docker compose down
```

Expected:

```
 ✔ Container blackbox-http  Removed
```

Nothing was built, so there is no local image. The pulled exporter image is shared with
Project 8 — remove it only after both are cleaned up (see "Optional" below).

---

## Step 2 — Remove the probe jobs from Prometheus

Re-comment **both** blocks in `infra/prometheus.yml`: `blackbox-http` and
`blackbox-exporter-http` (put `# ` back at the start of every line). Then:

```bash
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml
curl -X POST http://localhost:9090/-/reload
curl -s http://localhost:9090/api/v1/targets | grep -qE '"job":"blackbox-(http|exporter-http)"' && echo "still there" || echo "targets removed"
```

Expected: `targets removed`.

---

## Step 3 — Undo side effects

`http_post_job` submitted one job to Project 2 every scrape. They live in Project 2's memory
only; restart it to clear them if you want clean numbers:

```bash
docker restart job-processor
```

---

## Step 4 — The dashboard

**Blackbox HTTP Probes** is provisioned by `infra/` and stays until `infra/` is torn down.
Imported by hand elsewhere? Dashboard → Settings → Delete.

---

## Optional — remove the exporter image

Only once Project 8 is cleaned up too:

```bash
docker rmi prom/blackbox-exporter:v0.27.0
```

---

## Verify it's clean

```bash
docker ps -a --format '{{.Names}}' | grep -x blackbox-http || echo "no blackbox-http container"
```
