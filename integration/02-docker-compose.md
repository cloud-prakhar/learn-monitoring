# 02 — Run Prometheus + Grafana Together with Docker Compose

> **Read `01-docker-cli.md` first.** This file shows how the multi-container manual
> setup maps to a single Compose file — including the network plumbing.

---

## How the Compose file maps to `01-docker-cli.md`

### Network

| Manual command | Compose equivalent |
|---|---|
| `docker network create monitoring` | `networks: monitoring: driver: bridge` (bottom of file) |
| `--network monitoring` (on each run) | `networks: - monitoring` under each service |

### Prometheus service

| Manual command / flag | Compose equivalent |
|---|---|
| `docker volume create promdata` | `volumes: promdata:` at the bottom |
| `docker run -d` | service under `services:` |
| `--name prometheus` | service key `prometheus:` |
| `-p 9090:9090` | `ports: - "9090:9090"` |
| `-v $(pwd)/prometheus.yml:...` | `volumes: - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro` |
| `-v promdata:/prometheus` | `volumes: - promdata:/prometheus` |
| `--network monitoring` | `networks: - monitoring` |
| `prom/prometheus:v3.12.0` | `image: prom/prometheus:v3.12.0` |

### Grafana service

| Manual command / flag | Compose equivalent |
|---|---|
| `docker volume create grafdata` | `volumes: grafdata:` at the bottom |
| `--name grafana` | service key `grafana:` |
| `-p 3000:3000` | `ports: - "3000:3000"` |
| `-v grafdata:...` | `volumes: - grafdata:/var/lib/grafana` |
| `-v .../datasources:...` | `volumes: - ./grafana/provisioning/datasources:...:ro` |
| `-v .../dashboards (provider):...` | `volumes: - ./grafana/provisioning/dashboards:...:ro` |
| `-v .../dashboards (JSON):...` | `volumes: - ./grafana/dashboards:/var/lib/grafana/dashboards:ro` |
| `-e GF_SECURITY_ADMIN_USER=admin` | `environment: - GF_SECURITY_ADMIN_USER=admin` |
| `--network monitoring` | `networks: - monitoring` |
| (start Prometheus first) | `depends_on: - prometheus` |

### Key new Compose concept: `depends_on`

`depends_on: - prometheus` tells Compose to start the `prometheus` service before
starting `grafana`. This controls **start order**, not readiness — Prometheus may not
be fully ready when Grafana starts. For learning purposes this is fine; in production
you would use healthchecks to wait for true readiness.

---

## Step 1 — Clean up any old containers / networks

```bash
docker rm -f prometheus grafana 2>/dev/null
docker network rm monitoring 2>/dev/null
echo "clean"
```

---

## Step 2 — Start everything with one command

Make sure you are in the `integration/` directory.

```bash
docker compose up -d
```

**Expected output:**
```
[+] Running 6/6
 ✔ Network integration_monitoring    Created
 ✔ Volume "integration_promdata"     Created
 ✔ Volume "integration_grafdata"     Created
 ✔ Container prometheus              Started
 ✔ Container grafana                 Started
```

Notice that Compose:
- Created the network automatically
- Created both volumes
- Started Prometheus before Grafana (because of `depends_on`)

All of that was multiple manual steps before — now it is one command.

---

## Step 3 — Check status

```bash
docker compose ps
```

**Expected output:**
```
NAME         IMAGE                    STATUS    PORTS
grafana      grafana/grafana:13.0.1   running   0.0.0.0:3000->3000/tcp
prometheus   prom/prometheus:v3.12.0  running   0.0.0.0:9090->9090/tcp
```

---

## Step 4 — View logs

```bash
# All services at once
docker compose logs

# One service, follow live
docker compose logs -f grafana
```

---

## Step 5 — Verify

1. Open **http://localhost:3000** → log in → **Connections → Data sources** → Prometheus → **Save & test** → green.
2. **Dashboards → Provisioned → Prometheus Overview** → live charts.

---

## Step 6 — Stop and clean up

```bash
# Stop containers, keep volumes
docker compose down

# Stop AND delete volumes
docker compose down -v
```

| Compose command | What it does |
|---|---|
| `docker compose down` | Stops and removes containers AND the network |
| `docker compose down -v` | Also removes named volumes |

> **Notice:** `docker compose down` automatically removes the network (`monitoring`) that
> Compose created. You do not need `docker network rm` separately.

---

## Why the network section matters

The `networks:` block at the bottom of `docker-compose.yml` is what creates the virtual
network. The `networks: - monitoring` under each service is what attaches them to it.
Without both, containers would run in isolation and Grafana's data source URL
(`http://prometheus:9090`) would fail to resolve.

### Why the network is called `integration_monitoring`, not just `monitoring`

Look at the `up` output above: the network is named **`integration_monitoring`**, not
`monitoring`. Compose prefixes every network (and volume) it creates with the **project name**,
which defaults to the directory the compose file lives in:

```mermaid
flowchart LR
    DIR["project name<br/>= this directory<br/>integration/"]:::user
    KEY["network name<br/>from the networks: block<br/>monitoring"]:::net
    FULL["integration_monitoring<br/>the network Docker actually creates"]:::good

    DIR --> FULL
    KEY --> FULL

    classDef net fill:#EDE7FF,stroke:#7C4DFF,stroke-width:1.5px,color:#2A1065
    classDef user fill:#D4F5EE,stroke:#0D9488,stroke-width:1.5px,color:#06403A
    classDef good fill:#D9F5DC,stroke:#2E7D32,stroke-width:1.5px,color:#0E3B14
```

This is also why running the standalone `../prometheus-setup/` and `../grafana-setup/` stacks
separately can't talk to each other: neither of those compose files defines a `networks:`
block, so Compose falls back to creating a network named `<project>_default` for each —
`prometheus-setup_default` and `grafana-setup_default`. Two different networks, no shared DNS,
so `http://prometheus:9090` from Grafana fails with
`lookup prometheus ... server misbehaving`. The fix is to run both from a single compose file
that defines a shared network — exactly what this `integration/` setup does. (Full write-up:
[../docs/troubleshooting.md → section 4](../docs/troubleshooting.md#4-grafana-cannot-reach-prometheus--the-localhost-trap).)

---

**Next step:** First **tear this stack down** — it shares the container names `prometheus`
and `grafana` with `infra/`, so leaving it running makes the next `docker compose up -d`
fail with `Conflict. The container name "/prometheus" is already in use`:

```bash
docker compose down          # from integration/
```

Then head to **`../infra/`** to start the shared monitoring stack, then pick a project from
`projects/` (Projects 1–8, Docker) to build a real application that exposes custom metrics
and dashboards.
