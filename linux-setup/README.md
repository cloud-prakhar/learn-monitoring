# Native Prometheus + Grafana on Linux

This directory installs Prometheus and Grafana **directly on a Linux host** — bare-metal, a
cloud VM, or a local virtual machine — as systemd services. No Docker required.

> **On Windows + WSL2?** Use `wsl-setup/` instead. It is the same procedure with one extra
> consideration (some older WSL2 installs ship without systemd). On a real Linux box systemd is
> always present, so this guide is a touch simpler.

> **New to the repo?** This is one of three native paths: `linux-setup/` (here),
> `mac-setup/` (Homebrew), or `wsl-setup/` (Windows + WSL2). Or use the Docker path in `infra/`.
> They all end up with Prometheus on 9090 and Grafana on 3000.

---

## Docker vs Native — pick your path

| | Docker (`infra/`) | Native (this directory) |
|---|---|---|
| **Setup time** | ~2 min | ~10 min |
| **Restart after reboot** | `docker compose up -d` | systemd (auto) |
| **Config file location** | `infra/prometheus.yml` | `/etc/prometheus/prometheus.yml` |
| **Grafana data** | Docker named volume | `/var/lib/grafana/` |
| **Good for** | Quick start, projects 01–08 | Learning the binary, production-like setup |
| **Scrape target syntax** | `container-name:port` | `localhost:port` |

Both paths end up with the same result: Prometheus on port 9090, Grafana on port 3000.

---

## Setup order

1. **[Install Prometheus](01-install-prometheus.md)** — download binary, configure, systemd service
2. **[Install Grafana](02-install-grafana.md)** — install from APT (Debian/Ubuntu) or RPM (RHEL/Fedora)
3. **[Wire them together](03-wire-together.md)** — add Prometheus as a Grafana data source

Once done you have a working native Prometheus + Grafana. To add an application, point the
native Prometheus at any local exporter (see the commented examples in
[01-install-prometheus.md](01-install-prometheus.md)) — Projects 1–8 in `projects/` are the
Docker track and use `infra/` instead. Their ports are published on the host, so a native
Prometheus can also scrape a running project at `localhost:<port>` — the commented `8084` /
`8085` examples match Projects 4 and 5. (Projects 7–8 need container names to probe, so they
only work with `infra/`.)

When you're finished and want a clean machine, run **[04-cleanup.md](04-cleanup.md)** — it fully
uninstalls both services, users, binaries, config, and data.

---

## Prerequisites

- A 64-bit Linux distribution with **systemd** (Ubuntu 22.04+, Debian 12+, Fedora, RHEL/Rocky/Alma 9+, etc.)
  Confirm systemd is PID 1:
  ```bash
  ps --no-headers -o comm 1     # expected: systemd
  ```
- `sudo` access
- At least 512 MB free RAM and internet access for the first download/install

These instructions assume the `x86_64` (Intel/AMD) architecture. For ARM (`aarch64`), swap
`linux-amd64` for `linux-arm64` in the Prometheus download URL — the install guide flags exactly where.

---

## Which package manager?

The Prometheus step is identical everywhere (a single static binary). Only the **Grafana** step
branches by distro family:

| Distro family | Examples | Package tool | Grafana step |
|---|---|---|---|
| Debian-based | Ubuntu, Debian, Mint | APT | Step 2a |
| RHEL-based | Fedora, RHEL, Rocky, Alma, CentOS | DNF/YUM | Step 2b |

`02-install-grafana.md` covers both.
