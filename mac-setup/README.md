# Native Prometheus + Grafana on macOS

This directory installs Prometheus and Grafana **directly on macOS** using
[Homebrew](https://brew.sh) — no Docker required. Homebrew is the standard macOS package
manager; it installs the binaries, default config, and a launchd service definition (the
macOS equivalent of a Linux systemd unit) for each.

> **New to the repo?** This is one of three native paths. Pick the one for your OS:
> `mac-setup/` (here), `linux-setup/` (bare-metal / VM Linux), or `wsl-setup/` (Windows + WSL2).
> Or use the Docker path in `infra/`. They all end up with Prometheus on 9090 and Grafana on 3000.

---

## Docker vs Native — pick your path

| | Docker (`infra/`) | Native (this directory) |
|---|---|---|
| **Setup time** | ~2 min | ~5 min |
| **Restart after reboot** | `docker compose up -d` | `brew services` (auto) or manual command |
| **Config file location** | `infra/prometheus.yml` | `$(brew --prefix)/etc/prometheus.yml` |
| **Grafana data** | Docker named volume | `$(brew --prefix)/var/lib/grafana/` |
| **Good for** | Quick start, projects 01–08 | Learning the binary, no Docker Desktop |
| **Scrape target syntax** | `container-name:port` | `localhost:port` |

Both paths end up with the same result: Prometheus on port 9090, Grafana on port 3000.

---

## Setup order

1. **[Install Prometheus](01-install-prometheus.md)** — `brew install`, configure, run as a service
2. **[Install Grafana](02-install-grafana.md)** — `brew install`, start the server
3. **[Wire them together](03-wire-together.md)** — add Prometheus as a Grafana data source

Once done you have a working native Prometheus + Grafana. To add an application, point the
native Prometheus at any local exporter (see the commented examples in
[01-install-prometheus.md](01-install-prometheus.md)) — Projects 1–8 in `projects/` are the
Docker track and use `infra/` instead. Their ports are published on the host, so a native
Prometheus can also scrape a running project at `localhost:<port>` — the commented `8084` /
`8085` examples match Projects 4 and 5. (Projects 7–8 need container names to probe, so they
only work with `infra/`.)

When you're finished and want your machine back to a clean state, run
**[04-cleanup.md](04-cleanup.md)** — it fully uninstalls both services, binaries, config, and data.

---

## Prerequisites

- macOS 12 (Monterey) or newer, Apple Silicon (M-series) or Intel
- [Homebrew](https://brew.sh) installed. Check:
  ```bash
  brew --version
  ```
  If it is missing, install it with the one-liner on https://brew.sh, then re-run the check.
- Internet access for the first download/install

> **Homebrew prefix:** Homebrew installs to `/opt/homebrew` on Apple Silicon and `/usr/local`
> on Intel. Throughout these guides we write `$(brew --prefix)` so the commands work on both —
> the shell substitutes the right path for your Mac.
