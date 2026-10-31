# Clean Up — System Monitor (Project 4)

Reverses [CONNECT.md](CONNECT.md): stops the container, removes its image, and takes the scrape
job back out of Prometheus. The shared `infra/` stack keeps running.

---

## Step 1 — Stop and remove the container and its image

From `projects/04-system-monitor/`:

```bash
docker compose down --rmi local
```

Expected:

```
 ✔ Container system-monitor                   Removed
 ✔ Image 04-system-monitor-system-monitor     Removed
```

The `/proc` bind mount is read-only and only lasted as long as the container — nothing on the
host was changed. There is no data volume to remove.

---

## Step 2 — Remove the scrape job from Prometheus

Re-comment the block in `infra/prometheus.yml`:

```yaml
  # - job_name: "system-monitor"
  #   static_configs:
  #     - targets: ["system-monitor:8084"]
```

Reload and confirm the target is gone:

```bash
curl -X POST http://localhost:9090/-/reload
curl -s http://localhost:9090/api/v1/targets | grep -q '"job":"system-monitor"' && echo "still there" || echo "target removed"
```

Expected: `target removed`.

---

## Step 3 — The dashboard

The **System Monitor** dashboard is provisioned from `infra/grafana/dashboards/`, so it cannot be
deleted from the UI and simply shows "No data" now. It goes away with `infra/` (see
`infra/CLEANUP.md`). If you imported it by hand into another Grafana: dashboard → Settings →
Delete.

---

## Verify it's clean

```bash
docker ps -a --format '{{.Names}}' | grep -x system-monitor || echo "no system-monitor container"
docker images --format '{{.Repository}}' | grep 04-system-monitor || echo "no image"
```

Expected: `no system-monitor container` and `no image`.
