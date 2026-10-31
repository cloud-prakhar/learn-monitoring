# Clean Up — psutil System Monitor (Project 6)

Reverses [CONNECT.md](CONNECT.md). The shared `infra/` stack keeps running.

---

## Step 1 — Stop and remove the container and its image

From `projects/06-psutil-system-monitor/`:

```bash
docker compose down --rmi local
```

Expected:

```
 ✔ Container psutil-system-monitor                          Removed
 ✔ Image 06-psutil-system-monitor-psutil-system-monitor     Removed
```

The host `/proc` was mounted read-only — nothing on the host changed.

---

## Step 2 — Remove the scrape job from Prometheus

Re-comment the block in `infra/prometheus.yml`:

```yaml
  # - job_name: "psutil-system-monitor"
  #   static_configs:
  #     - targets: ["psutil-system-monitor:8086"]
```

```bash
curl -X POST http://localhost:9090/-/reload
curl -s http://localhost:9090/api/v1/targets | grep -q '"job":"psutil-system-monitor"' && echo "still there" || echo "target removed"
```

Expected: `target removed`.

---

## Step 3 — The dashboard

**psutil System Monitor** is provisioned by `infra/` and stays until `infra/` is torn down.
Imported by hand elsewhere? Dashboard → Settings → Delete.

---

## Verify it's clean

```bash
docker ps -a --format '{{.Names}}' | grep -x psutil-system-monitor || echo "no psutil-system-monitor container"
docker images --format '{{.Repository}}' | grep 06-psutil-system-monitor || echo "no image"
```
