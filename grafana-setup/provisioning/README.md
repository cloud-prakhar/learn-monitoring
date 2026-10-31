# grafana-setup/provisioning/

This directory is a placeholder for the standalone Grafana setup.

In the **standalone** Grafana setup (`grafana-setup/`), no provisioning is configured —
students add the Prometheus data source manually to understand the concept before
it is automated.

Provisioning is introduced and fully used in:
- `../integration/grafana/provisioning/` — auto-wires Prometheus as a data source
- `../infra/grafana/provisioning/` — same, for the shared infra stack (projects 01–08)

See `../integration/README.md` for a full explanation of how provisioning works.
