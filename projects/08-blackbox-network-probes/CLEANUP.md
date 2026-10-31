# Clean Up — Blackbox Network Probes (Project 8)

Reverses [CONNECT.md](CONNECT.md). The shared `infra/` stack and the probed projects keep running.

---

## Step 1 — Stop and remove the exporter

From `projects/08-blackbox-network-probes/`:

```bash
docker compose down
```

Expected:

```
 ✔ Container blackbox-network  Removed
```

---

## Step 2 — Remove the probe jobs from Prometheus

Re-comment the four blocks in `infra/prometheus.yml` — `blackbox-tcp`, `blackbox-icmp`,
`blackbox-dns`, `blackbox-exporter-network` — then:

```bash
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml
curl -X POST http://localhost:9090/-/reload
curl -s http://localhost:9090/api/v1/targets | grep -qE '"job":"blackbox-(tcp|icmp|dns|exporter-network)"' && echo "still there" || echo "targets removed"
```

Expected: `targets removed`.

---

## Step 3 — The dashboard

**Blackbox Network Probes** is provisioned by `infra/` and stays until `infra/` is torn down.
Imported by hand elsewhere? Dashboard → Settings → Delete.

---

## Optional — remove the exporter image

Once Project 7 is cleaned up too:

```bash
docker rmi prom/blackbox-exporter:v0.27.0
```

---

## Verify it's clean

```bash
docker ps -a --format '{{.Names}}' | grep -x blackbox-network || echo "no blackbox-network container"
```
