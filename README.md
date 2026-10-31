# learn-monitoring — Setup & Installation Lab (Prometheus + Grafana)

Everything you need to **install and wire up** Prometheus and Grafana locally, plus eight
Docker projects that produce real data to look at: three instrumented applications, three
system monitors, and two probe-monitoring projects built on the Blackbox Exporter. No cloud accounts, no
subscriptions — it all runs on your machine.

Two setup paths: **Docker** (quickest start) or **Native** (install the binaries as system
services — closer to production). Pick one and follow it consistently.

> **Scope:** this repo is the setup/installation track plus the Docker projects. Monitoring
> theory (monitoring-fundamentals) and the ELK pillar are not included here. Projects 4–6 are
> container editions of the native-track system monitors, run against the same `infra/` stack.

---

## Repository structure

```mermaid
flowchart LR
    ROOT(["learn-monitoring"]):::net

    ROOT --> DOCS["docs/"]:::doc
    ROOT --> DOCKER["Docker path"]:::app
    ROOT --> NATIVE["Native path"]:::user
    ROOT --> PROJ["projects/<br/>scraped by infra/"]:::app
    ROOT --> SCR["scripts/<br/>validate-connectivity.sh"]:::doc

    DOCS --> DOC1["wsl-setup.md<br/>Windows: WSL2 + Docker Desktop"]:::doc
    DOCS --> DOC2["troubleshooting.md<br/>error messages and fix commands"]:::doc

    DOCKER --> DK1["prometheus-setup/<br/>Prometheus standalone"]:::prom
    DOCKER --> DK2["grafana-setup/<br/>Grafana standalone"]:::graf
    DOCKER --> DK3["integration/<br/>wire the two together"]:::net
    DOCKER --> DK4["infra/<br/>shared stack for projects 1-8"]:::net

    NATIVE --> NT1["wsl-setup/<br/>Windows + WSL2 · systemd"]:::user
    NATIVE --> NT2["linux-setup/<br/>bare-metal / VM Linux · systemd"]:::user
    NATIVE --> NT3["mac-setup/<br/>macOS · Homebrew / launchd"]:::user
    NT3 --> NTG["same 4 guides in each:<br/>01-install-prometheus.md<br/>02-install-grafana.md<br/>03-wire-together.md<br/>04-cleanup.md"]:::doc

    PROJ --> PR1["01-flask-web-api/<br/>request rate · latency · error rate"]:::app
    PROJ --> PR2["02-job-processor/<br/>queue depth · throughput · failures"]:::app
    PROJ --> PR3["03-cache-service/<br/>hit rate · key count · TTL evictions"]:::app
    PROJ --> PR4["04-system-monitor/<br/>host CPU · memory · disk via raw /proc"]:::user
    PROJ --> PR5["05-url-health-checker/<br/>hand-made HTTP up/down checks"]:::user
    PROJ --> PR6["06-psutil-system-monitor/<br/>host metrics via psutil"]:::user
    PROJ --> PR7["07-blackbox-http-probes/<br/>Blackbox Exporter: HTTP · body · TLS"]:::prom
    PROJ --> PR8["08-blackbox-network-probes/<br/>Blackbox Exporter: TCP · ICMP · DNS"]:::prom

    classDef prom fill:#FFE0D3,stroke:#D64518,stroke-width:1.5px,color:#4A1405
    classDef graf fill:#FFF0C2,stroke:#C98A00,stroke-width:1.5px,color:#4A3300
    classDef app fill:#D9E8FF,stroke:#2563EB,stroke-width:1.5px,color:#0B2559
    classDef net fill:#EDE7FF,stroke:#7C4DFF,stroke-width:1.5px,color:#2A1065
    classDef user fill:#D4F5EE,stroke:#0D9488,stroke-width:1.5px,color:#06403A
    classDef doc fill:#E2F0FB,stroke:#0369A1,stroke-width:1.5px,color:#06314A
```

Every setup directory and project has the same shape: a `README.md` explaining it, numbered
guides or a `CONNECT.md` for the hands-on steps, and a `CLEANUP.md` to tear it back down.

---

## Choose your path

### Path A — Docker (recommended for beginners)

Prometheus and Grafana run in containers managed by `infra/`. Projects join a shared Docker
network so Prometheus can scrape them by container name.

**Prerequisites:** Docker Desktop installed. On Windows, complete `docs/wsl-setup.md` first.

```bash
docker run hello-world   # verify Docker works
docker compose version   # verify Compose v2
```

### Path B — Native (no Docker for Prometheus/Grafana)

Prometheus and Grafana run as system processes directly on your OS. All three directories end
up with Prometheus on 9090 and Grafana on 3000:

| Your machine | Setup directory | Service manager | Prometheus config path |
|---|---|---|---|
| Windows + WSL2 (Ubuntu) | `wsl-setup/` | systemd | `/etc/prometheus/prometheus.yml` |
| Bare-metal / VM Linux | `linux-setup/` | systemd | `/etc/prometheus/prometheus.yml` |
| macOS | `mac-setup/` | launchd (`brew services`) | `$(brew --prefix)/etc/prometheus.yml` |

```bash
# Linux / WSL2 — verify systemd is PID 1:
ps --no-headers -o comm 1     # expected: systemd

# macOS — verify Homebrew is installed:
brew --version
```

---

## Recommended order

### Docker path

```mermaid
flowchart LR
    S1["1 · docs/wsl-setup.md<br/>Windows only: WSL2 + Docker Desktop"]:::doc
    S2["2 · prometheus-setup/<br/>run Prometheus by hand, then with Compose"]:::prom
    S3["3 · grafana-setup/<br/>first login, manual data source"]:::graf
    S4["4 · integration/<br/>why container networking needs a shared network"]:::net
    S5["5 · infra/README.md<br/>start the shared monitoring stack"]:::net
    S6["6 · projects/01-flask-web-api/CONNECT.md<br/>HTTP metrics, first dashboard"]:::app
    S7["7 · projects/02-job-processor/CONNECT.md<br/>queue + async metrics, histograms"]:::app
    S8["8 · projects/03-cache-service/CONNECT.md<br/>hit ratio, gauges, TTL evictions"]:::app
    S9["9 · projects/04-system-monitor/CONNECT.md<br/>host metrics from raw /proc"]:::user
    S10["10 · projects/05-url-health-checker/CONNECT.md<br/>hand-made availability checks"]:::user
    S11["11 · projects/06-psutil-system-monitor/CONNECT.md<br/>same metrics via psutil, compare with 9"]:::user
    S12["12 · projects/07-blackbox-http-probes/CONNECT.md<br/>black-box HTTP probes"]:::prom
    S13["13 · projects/08-blackbox-network-probes/CONNECT.md<br/>TCP, ICMP and DNS probes"]:::prom
    S14["each CLEANUP.md, then infra/CLEANUP.md<br/>when you are finished"]:::bad

    S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7 --> S8
    S8 --> S9 --> S10 --> S11 --> S12 --> S13
    S13 -.-> S14

    classDef prom fill:#FFE0D3,stroke:#D64518,stroke-width:1.5px,color:#4A1405
    classDef graf fill:#FFF0C2,stroke:#C98A00,stroke-width:1.5px,color:#4A3300
    classDef app fill:#D9E8FF,stroke:#2563EB,stroke-width:1.5px,color:#0B2559
    classDef net fill:#EDE7FF,stroke:#7C4DFF,stroke-width:1.5px,color:#2A1065
    classDef doc fill:#E2F0FB,stroke:#0369A1,stroke-width:1.5px,color:#06314A
    classDef user fill:#D4F5EE,stroke:#0D9488,stroke-width:1.5px,color:#06403A
    classDef bad fill:#FFD9D9,stroke:#D32F2F,stroke-width:1.5px,color:#5A0F0F
```

### Native path

Use the directory for your OS (`wsl-setup/`, `linux-setup/` or `mac-setup/`) — the file names
are identical:

```mermaid
flowchart LR
    N1["1 · 01-install-prometheus.md<br/>install Prometheus, run as a service"]:::prom
    N2["2 · 02-install-grafana.md<br/>install Grafana, start the server"]:::graf
    N3["3 · 03-wire-together.md<br/>add the data source, first query"]:::net
    N4["04-cleanup.md<br/>when done: uninstall everything"]:::bad

    N1 --> N2 --> N3
    N3 -.->|"when you are finished"| N4

    classDef prom fill:#FFE0D3,stroke:#D64518,stroke-width:1.5px,color:#4A1405
    classDef graf fill:#FFF0C2,stroke:#C98A00,stroke-width:1.5px,color:#4A3300
    classDef net fill:#EDE7FF,stroke:#7C4DFF,stroke-width:1.5px,color:#2A1065
    classDef bad fill:#FFD9D9,stroke:#D32F2F,stroke-width:1.5px,color:#5A0F0F
```

Projects 1–8 are the Docker track — they run as containers scraped by `infra/`. With a native
Prometheus you point `prometheus.yml` at `localhost:<port>` instead (each native install guide
ships a commented example job showing the syntax).

---

## The projects

| # | Project | Stack | What it teaches |
|---|---|---|---|
| 1 | `projects/01-flask-web-api/` | Flask + `prometheus_client` | Counter, Histogram, Gauge — request rate, p95 latency, error rate |
| 2 | `projects/02-job-processor/` | Python + worker thread queue | Queue depth, throughput, job duration, failure rate |
| 3 | `projects/03-cache-service/` | Flask in-memory cache with TTL | Hit/miss ratio, key count, TTL evictions |
| 4 | `projects/04-system-monitor/` | Flask reading the host's `/proc` | **System monitoring** the way Node Exporter does it: CPU, memory, swap, load, disk I/O |
| 5 | `projects/05-url-health-checker/` | Flask + `requests` poller | Availability checks by container name: up/down, status codes, response time |
| 6 | `projects/06-psutil-system-monitor/` | Flask + `psutil` | The same host metrics through a portable library, plus disk usage and network |
| 7 | `projects/07-blackbox-http-probes/` | Prometheus Blackbox Exporter | **Probe monitoring**: HTTP status, body matching, POST checks, TLS expiry, relabeling |
| 8 | `projects/08-blackbox-network-probes/` | Prometheus Blackbox Exporter | TCP port, ICMP ping and DNS probes; layered diagnosis; expected-failure labels |

Projects 1–6 are **white-box**: the app reports on itself (or its host) at `/metrics`. Projects
7–8 are **black-box**: an outside prober tests the *same containers* the way a user would.

Each project directory contains:

- `README.md` — what it does, which metrics it exposes and **why**
- `CONNECT.md` — step-by-step: start it, add the scrape job, **validate connectivity hop by
  hop**, explore the data, open the dashboard
- `docker-compose.yml` — the project's own stack (joins the `monitoring` network)
- `app/` (Projects 1–6) — application source, `requirements.txt` and `Dockerfile`;
  `blackbox.yml` (Projects 7–8) — probe module definitions
- `dashboards/` — the Grafana dashboard JSON for that project
- `CLEANUP.md` — stop and remove everything it created

### Validate connectivity

`scripts/validate-connectivity.sh` checks every hop from a project to its Grafana dashboard —
network, Prometheus → app, target UP, Grafana → Prometheus, Grafana query, dashboard loaded:

```bash
scripts/validate-connectivity.sh system-monitor system-monitor:8084 system-monitor
```

Each `CONNECT.md` shows the exact arguments for that project, plus the manual commands behind
each check.

`infra/grafana/dashboards/` provisions every project's dashboard, plus a combined
**all-projects overview** (Projects 1–3), automatically when the shared stack starts.

---

## Ports used

| Service | Port |
|---|---|
| Prometheus | 9090 |
| Grafana | 3000 (login `admin` / `admin`) |
| Project 1 — Flask Web API | 8081 |
| Project 2 — Job Processor | 8082 |
| Project 3 — Cache Service | 8083 |
| Project 4 — System Monitor | 8084 |
| Project 5 — URL Health Checker | 8085 |
| Project 6 — psutil System Monitor | 8086 |
| Project 7 — Blackbox Exporter (HTTP probes) | 9115 |
| Project 8 — Blackbox Exporter (network probes) | 9116 (9115 inside the network) |

---

## When something breaks

`docs/troubleshooting.md` is organized by the exact error message you see — ports already in
use, containers not starting, `external network "monitoring" not found`, empty dashboards, YAML
errors, volume permissions, WSL2 path issues, system-monitor values, blackbox probe failures,
and a full-reset procedure.
