# Native Prometheus + Grafana on WSL2

This directory installs Prometheus and Grafana **directly inside WSL2** as system processes — no Docker required. This gives you full control over the binaries, config files, and service lifecycle.

---

## Docker vs Native — pick your path

| | Docker (`infra/`) | Native (this directory) |
|---|---|---|
| **Setup time** | ~2 min | ~10 min |
| **Restart after reboot** | `docker compose up -d` | systemctl or manual command |
| **Config file location** | `infra/prometheus.yml` | `/etc/prometheus/prometheus.yml` |
| **Grafana data** | Docker named volume | `/var/lib/grafana/` |
| **Good for** | Quick start, projects 01–08 | Learning the binary, production-like setup |
| **Scrape target syntax** | `container-name:port` | `localhost:port` |

Both paths end up with the same result: Prometheus on port 9090, Grafana on port 3000.

---

## Setup order

1. **[Install Prometheus](01-install-prometheus.md)** — download binary, configure, run as a service
2. **[Install Grafana](02-install-grafana.md)** — install via apt, start the server
3. **[Wire them together](03-wire-together.md)** — add Prometheus as a Grafana data source

Once done you have a working native Prometheus + Grafana. To add an application, point the
native Prometheus at any local exporter (see the commented examples in
[01-install-prometheus.md](01-install-prometheus.md)) — Projects 1–8 in `projects/` are the
Docker track and use `infra/` instead. Their ports are published on the host, so a native
Prometheus can also scrape a running project at `localhost:<port>` — the commented `8084` /
`8085` examples match Projects 4 and 5. (Projects 7–8 need container names to probe, so they
only work with `infra/`.)

When you're finished and want your machine back to a clean state, run
**[04-cleanup.md](04-cleanup.md)** — it fully uninstalls both services, users, binaries, config,
and data.

---

## Prerequisites

- WSL2 with Ubuntu 22.04 or 24.04 (run `lsb_release -a` to check)
- At least 512 MB free RAM
- Internet access for the first download/install

These instructions assume the `x86_64` (Intel/AMD) architecture, which is standard for WSL2 on Windows.
