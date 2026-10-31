# Clean Up — URL Health Checker (Project 5)

Reverses [CONNECT.md](CONNECT.md). The shared `infra/` stack keeps running.

---

## Step 1 — Stop and remove the container and its image

From `projects/05-url-health-checker/`:

```bash
docker compose down --rmi local
```

Expected:

```
 ✔ Container url-health-checker                       Removed
 ✔ Image 05-url-health-checker-url-health-checker     Removed
```

URLs added with `POST /targets` were held in memory and are gone with the container.

---

## Step 2 — Remove the scrape job from Prometheus

Re-comment the block in `infra/prometheus.yml`:

```yaml
  # - job_name: "url-health-checker"
  #   static_configs:
  #     - targets: ["url-health-checker:8085"]
```

```bash
curl -X POST http://localhost:9090/-/reload
curl -s http://localhost:9090/api/v1/targets | grep -q '"job":"url-health-checker"' && echo "still there" || echo "target removed"
```

Expected: `target removed`.

---

## Step 3 — The dashboard

**URL Health Checker** is provisioned by `infra/` — it stays and shows "No data" until `infra/`
is torn down. Imported by hand elsewhere? Dashboard → Settings → Delete.

---

## Verify it's clean

```bash
docker ps -a --format '{{.Names}}' | grep -x url-health-checker || echo "no url-health-checker container"
docker images --format '{{.Repository}}' | grep 05-url-health-checker || echo "no image"
```
