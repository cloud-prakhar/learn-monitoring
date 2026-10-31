# Troubleshooting Reference

This document covers every common failure mode encountered when running the stacks in this
repository. Each section shows the exact error message, explains the root cause, and gives
specific commands to diagnose and fix the problem.

---

## Table of Contents

1. [Quick diagnostic checklist](#1-quick-diagnostic-checklist)
2. [Port already in use](#2-port-already-in-use)
3. [Container exits immediately after starting](#3-container-exits-immediately-after-starting)
4. [Grafana cannot reach Prometheus — the localhost trap](#4-grafana-cannot-reach-prometheus--the-localhost-trap)
   - [Variant — `server misbehaving`: containers on separate networks](#variant--server-misbehaving-containers-on-separate-networks)
5. [Prometheus targets show as DOWN](#5-prometheus-targets-show-as-down)
6. [Grafana shows "No data" on panels](#6-grafana-shows-no-data-on-panels)
7. [Provisioned data source or dashboard not appearing](#7-provisioned-data-source-or-dashboard-not-appearing)
8. [Config file not found — bind mount failures](#8-config-file-not-found--bind-mount-failures)
9. [Volume permission errors — Grafana cannot write](#9-volume-permission-errors--grafana-cannot-write)
10. [Python project image fails to build](#10-python-project-image-fails-to-build)
11. [YAML syntax errors in prometheus.yml or docker-compose.yml](#11-yaml-syntax-errors-in-prometheusyml-or-docker-composeyml)
12. [docker-compose command not found](#12-docker-compose-command-not-found)
13. [WSL2-specific path issues](#13-wsl2-specific-path-issues)
14. [external network "monitoring" not found](#14-external-network-monitoring-not-found)
15. [How to read logs effectively](#15-how-to-read-logs-effectively)
16. [Full reset — start from scratch](#16-full-reset--start-from-scratch)
17. [System monitors (Projects 4 and 6) show odd values](#17-system-monitors-projects-4-and-6-show-odd-values)
18. [Blackbox probes fail or show no data (Projects 7 and 8)](#18-blackbox-probes-fail-or-show-no-data-projects-7-and-8)
19. [Edited prometheus.yml but the reload changed nothing](#19-edited-prometheusyml-but-the-reload-changed-nothing)

---

## 1. Quick diagnostic checklist

Run these commands first, before anything else. They give a complete picture of the current state.

```bash
# Is Docker running?
docker info

# What is currently running?
docker ps

# What containers exist, including stopped ones?
docker ps -a

# What networks exist?
docker network ls

# What volumes exist?
docker volume ls

# Logs for a specific container (replace 'prometheus' with your container name):
docker logs prometheus

# Compose status from the project directory:
docker compose ps
docker compose logs
```

If `docker info` hangs or returns an error, Docker Desktop is not running. Start it first.

---

## 2. Port already in use

### Error message

When running `docker compose up -d` or `docker run`:

```
Error response from daemon: driver failed programming external connectivity on endpoint prometheus
(abc123): Bind for 0.0.0.0:9090 failed: port is already allocated
```

Or:

```
Error response from daemon: failed to create endpoint prometheus on network bridge:
Bind for 0.0.0.0:9090 failed: port is already allocated
```

### Root cause

Something else on your machine is already listening on that port. This can be:
- Another Docker container you forgot to stop
- A system service (e.g. a local Prometheus installation, a dev server)
- A previous container that stopped but whose port was not released yet

### Diagnosis

**Find what is using the port (Linux / WSL2):**
```bash
sudo lsof -i :9090      # shows which process holds the port
sudo lsof -i :3000
sudo lsof -i :8081      # Flask Web API
sudo lsof -i :8082      # Job Processor
sudo lsof -i :8083      # Cache Service
sudo lsof -i :8084      # System Monitor
sudo lsof -i :8085      # URL Health Checker
sudo lsof -i :8086      # psutil System Monitor
sudo lsof -i :9115      # Blackbox Exporter — HTTP probes (Project 7)
sudo lsof -i :9116      # Blackbox Exporter — network probes (Project 8)
```

**Find what is using the port (Windows PowerShell, if not using WSL2):**
```powershell
netstat -ano | findstr :9090
# The last column is the PID — look it up in Task Manager
```

**Check for a stopped or running container using that port:**
```bash
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep 9090
```

### Fix — Option A: Stop the conflicting container

```bash
# If it is another Docker container:
docker stop <container-name>
docker rm <container-name>

# Then retry:
docker compose up -d
```

### Fix — Option B: Force-remove any container with that name

If a previous run left a container in a bad state:
```bash
docker rm -f prometheus
docker rm -f grafana
docker rm -f flask-web-api job-processor cache-service
```

### Fix — Option C: Change the host port

Edit `docker-compose.yml` and change the host-side port number (left of the colon):

```yaml
ports:
  - "9091:9090"   # Prometheus now accessible at http://localhost:9091
```

Remember to update any URLs or `prometheus.yml` targets accordingly if you change ports.

---

## 3. Container exits immediately after starting

### Symptom

`docker compose up -d` appears to succeed, but `docker compose ps` shows:

```
NAME         IMAGE                    STATUS             PORTS
prometheus   prom/prometheus:v3.12.0  Exited (1) 2s ago
```

Or `docker ps` shows nothing because the container stopped immediately.

### Diagnosis

The container started and then crashed. The exit code tells you which type of problem:

| Exit code | General meaning |
|-----------|----------------|
| 1 | Application error — check the logs |
| 2 | Config or argument error |
| 137 | Killed (OOM or `docker stop` / `docker kill`) |

**Always read the logs first:**
```bash
docker logs prometheus
# Or via Compose:
docker compose logs prometheus
```

### Common causes and fixes

#### Cause: Config file has a YAML error

Error in logs:
```
msg="Error loading config (--config.file=/etc/prometheus/prometheus.yml)"
err="parsing YAML file /etc/prometheus/prometheus.yml: ..."
```

Fix: Validate the YAML file:
```bash
# Install yamllint if you don't have it:
pip3 install yamllint

# Then validate:
yamllint prometheus.yml
```

Or just look for the common YAML mistakes (see [section 11](#11-yaml-syntax-errors-in-prometheusyml-or-docker-composeyml)).

#### Cause: Config file not found inside the container

Error in logs:
```
msg="Error loading config" err="open /etc/prometheus/prometheus.yml: no such file or directory"
```

This means the volume mount did not work. See [section 8](#8-config-file-not-found--bind-mount-failures).

#### Cause: Port conflict discovered at startup

Error in logs:
```
bind: address already in use
```

See [section 2](#2-port-already-in-use).

#### Cause: Prometheus data directory permissions

Error in logs:
```
opening storage failed: open /prometheus/queries.active: permission denied
```

Fix:
```bash
# Delete the volume and let Docker recreate it:
docker compose down -v
docker compose up -d
```

If you are using a host-directory bind mount for `/prometheus` data (not recommended),
you need to make the directory writable by UID 65534 (the `nobody` user Prometheus runs as):
```bash
sudo chown -R 65534:65534 ./prometheus-data
```

---

## 4. Grafana cannot reach Prometheus — the localhost trap

This is the single most common problem when connecting Grafana to Prometheus.

### Symptom

In Grafana → Connections → Data sources → Prometheus → Save & test:

```
Post "http://localhost:9090/api/v1/query": dial tcp 127.0.0.1:9090: connect: connection refused
```

Or:

```
Get "http://localhost:9090/api/v1/labels": context deadline exceeded
```

### Root cause — detailed explanation

Each Docker container has its own isolated network namespace. Inside a container,
`localhost` (or `127.0.0.1`) refers to **the container itself** — not the host machine,
and not any other container.

When Grafana tries to connect to `http://localhost:9090`, it is asking:
> "Is there anything listening on port 9090 inside *me* (the Grafana container)?"

There is not. Prometheus is running in a completely separate container with its own
`localhost`. The request never reaches Prometheus.

```mermaid
flowchart LR
    subgraph THINK["What you think is happening"]
        direction LR
        BROWSER["Your browser<br/>on your machine"]:::user
        PROM1["Prometheus<br/>:9090"]:::prom
        BROWSER -->|"localhost:9090 ✓ this works"| PROM1
    end

    subgraph REAL["What Grafana actually does"]
        direction LR
        GRAF["Grafana<br/>container"]:::graf
        VOID["localhost:9090<br/>inside the Grafana container<br/>nothing listens here"]:::bad
        GRAF -->|"localhost:9090 ✗ fails"| VOID
    end

    style THINK fill:#F2FBF8,stroke:#0D9488,color:#06403A
    style REAL fill:#FFF5F5,stroke:#D32F2F,color:#5A0F0F
    classDef prom fill:#FFE0D3,stroke:#D64518,stroke-width:1.5px,color:#4A1405
    classDef graf fill:#FFF0C2,stroke:#C98A00,stroke-width:1.5px,color:#4A3300
    classDef user fill:#D4F5EE,stroke:#0D9488,stroke-width:1.5px,color:#06403A
    classDef bad fill:#FFD9D9,stroke:#D32F2F,stroke-width:1.5px,color:#5A0F0F
```

### The fix — use the service name

Docker creates a DNS entry for every service name (or container name) on a shared
network. When Grafana and Prometheus are on the same Docker network, Docker resolves
`prometheus` to the Prometheus container's internal IP address.

The correct Prometheus URL to enter in Grafana is:

```
http://prometheus:9090
```

Not:
- ~~`http://localhost:9090`~~
- ~~`http://127.0.0.1:9090`~~
- ~~`http://host.docker.internal:9090`~~ (this reaches your host machine's port 9090, which is not where Prometheus is listening from inside the container)

### Verify the containers are on the same network

```bash
# Check what network 'prometheus' is on:
docker inspect prometheus --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}'

# Check what network 'grafana' is on:
docker inspect grafana --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}'
```

Both must return the same network name (e.g. `integration_monitoring`).

If they are on different networks, the containers cannot reach each other by name.
Make sure you are running `docker compose up -d` from the correct directory (the one
with the `docker-compose.yml` that defines both services together).

### Verify DNS resolution from inside Grafana

```bash
docker exec grafana wget -qO- http://prometheus:9090/-/healthy
```

Expected output:
```
Prometheus Server is Healthy.
```

If this fails with `Name or service not known`, the containers are not on the same network.

If this succeeds but Grafana still shows an error, the data source URL in Grafana is wrong
— check it is exactly `http://prometheus:9090` with no trailing slash.

### Check the provisioning file (integration/ and infra/)

If you are using provisioning, the URL is in:
- `integration/grafana/provisioning/datasources/prometheus.yml`
- `infra/grafana/provisioning/datasources/prometheus.yml`

Open the file and confirm:
```yaml
url: http://prometheus:9090
```

If you see `localhost`, change it to `prometheus` and restart Grafana:
```bash
docker compose restart grafana
```

---

### Variant — `server misbehaving`: containers on separate networks

This is a *different* failure from the localhost trap above. Here the URL is already
correct (`http://prometheus:9090`), but the lookup of the name `prometheus` itself fails.

#### Symptom

In Grafana → Connections → Data sources → Prometheus → Save & test:

```
Post "http://prometheus:9090/api/v1/query": dial tcp: lookup prometheus on
127.0.0.11:53: server misbehaving
```

The tell-tale part is **`lookup prometheus on 127.0.0.11:53`**. `127.0.0.11` is Docker's
built-in DNS server inside the container. The error means Grafana asked Docker's DNS to
resolve the name `prometheus` and got nothing back.

#### Root cause

Docker's embedded DNS only resolves a container's name **for other containers on the same
network**. If Grafana and Prometheus are on *different* networks, Docker's DNS has no entry
for `prometheus` from Grafana's point of view, so the lookup fails with `server misbehaving`.

The usual way to end up here is starting the two tools from their **standalone** directories:

```bash
# This creates TWO isolated networks — the trap:
docker compose -f prometheus-setup/docker-compose.yml up -d   # → prometheus-setup_default
docker compose -f grafana-setup/docker-compose.yml up -d      # → grafana-setup_default
```

Each standalone `docker-compose.yml` defines only one service, so Compose gives each its own
`<dir>_default` network. The containers can't see each other by name.

> The standalone `prometheus-setup/` and `grafana-setup/` stacks are for learning each tool
> **in isolation**. To run them *together*, use `integration/` (or later `infra/`), whose
> single compose file puts both on one shared `monitoring` network.

#### Diagnosis

```bash
# Show each running container and the network(s) it is attached to:
docker ps --format 'table {{.Names}}\t{{.Networks}}'
```

Problem looks like this — two different networks:
```
NAMES        NETWORKS
grafana      grafana-setup_default
prometheus   prometheus-setup_default
```

Fixed looks like this — one shared network:
```
NAMES        NETWORKS
grafana      integration_monitoring
prometheus   integration_monitoring
```

#### Fix — Option A (recommended): run the integration stack

Tear down the two standalone stacks (this frees the `prometheus`/`grafana` names; your named
volumes are preserved because there is no `-v` flag), then bring both up together:

```bash
docker compose -f prometheus-setup/docker-compose.yml down
docker compose -f grafana-setup/docker-compose.yml down

cd integration
docker compose up -d
```

#### Fix — Option B (quick patch): join the running containers to one network

Keeps the current containers; just attaches both to the shared `monitoring` network:

```bash
docker network connect monitoring prometheus
docker network connect monitoring grafana
```

⚠️ This patch is lost the next time the containers are recreated. Option A is the durable fix
and matches how this repo is meant to run.

#### Verify the fix

```bash
# 1. DNS + connectivity from inside Grafana (the exact path that was failing):
docker exec grafana wget -qO- http://prometheus:9090/-/healthy
# Expected: Prometheus Server is Healthy.

# 2. Datasource health straight from the Grafana API (no UI clicking):
curl -s -u admin:admin \
  http://localhost:3000/api/datasources/uid/PBFA97CFB590B2093/health
# Expected: {"message":"Successfully queried the Prometheus API.","status":"OK"}
```

(The datasource UID `PBFA97CFB590B2093` is the one the `integration/`/`infra/` provisioning
assigns to Prometheus. List your datasources with
`curl -s -u admin:admin http://localhost:3000/api/datasources` if yours differs.)

---

## 5. Prometheus targets show as DOWN

### How to see the targets page

Open `http://localhost:9090/targets` in your browser. Each target will show one of:
- **UP** — Prometheus successfully scraped it
- **DOWN** — Prometheus could not reach it
- **UNKNOWN** — First scrape has not happened yet (wait 15–30 seconds)

### Diagnosis

Click on the target row to expand it and read the error message.

```bash
# Also visible via API:
curl -s http://localhost:9090/api/v1/targets | python3 -m json.tool | grep -A5 '"health"'
```

### Common target errors and fixes

#### Error: `connection refused`

```
Get "http://flask-web-api:8081/metrics": dial tcp 172.18.0.3:8081: connect: connection refused
```

**Cause:** The project container is not running, or the wrong port is configured in `prometheus.yml`.

**Fix:**
```bash
# Is the container running?
docker ps | grep flask-web-api    # or job-processor / cache-service

# If not, start it from the project directory:
cd projects/01-flask-web-api
docker compose up -d --build
```

#### Error: `no such host`

```
Get "http://flask-web-api:8081/metrics": dial tcp: lookup flask-web-api: no such host
```

**Cause:** Prometheus cannot resolve the hostname. The project container is not on the
`monitoring` network — usually because the `monitoring` network did not exist when the
project container started, so Docker created it on a different network instead.

**Fix:**
```bash
# Confirm infra is running and the network exists:
docker network ls | grep monitoring

# Confirm the project container is on the monitoring network:
docker inspect flask-web-api --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'

# If it is on the wrong network, restart it after infra is up:
cd projects/01-flask-web-api
docker compose down
docker compose up -d --build
```

Both prometheus and the project container must show `monitoring` in their network list.

#### Error: `context deadline exceeded`

```
Get "http://flask-web-api:8081/metrics": context deadline exceeded
```

**Cause:** Prometheus can resolve the hostname but the app is not responding within the
scrape timeout. The container is running but the `/metrics` endpoint is broken or slow.

**Fix:**
```bash
# Test reachability from inside the Prometheus container:
docker exec prometheus wget -qO- http://flask-web-api:8081/metrics | head -5

# Check the project app logs:
docker logs flask-web-api
```

#### Error: `404 Not Found`

```
non-2xx response: HTTP status 404
```

**Cause:** The target is reachable but there is no `/metrics` endpoint at the specified path.

**Fix:** Check the `metrics_path` in `prometheus.yml`. By default Prometheus scrapes `/metrics`.
If your app exposes metrics at a different path, add:

```yaml
- job_name: "my-app"
  metrics_path: /my-custom-metrics-path
  static_configs:
    - targets: ["my-app:8080"]
```

#### Reload Prometheus config without restarting

If you edit `prometheus.yml`, you do not need to restart the container:

```bash
docker exec prometheus kill -HUP 1
```

This sends a SIGHUP signal that causes Prometheus to reload its config. Check the logs:
```bash
docker logs prometheus | grep -i "reload\|config"
```

---

## 6. Grafana shows "No data" on panels

### Symptom

A dashboard loads but panels are empty, show `No data`, or display the message
`Data is outside the time range`.

### Diagnosis steps — work through these in order

**Step 1: Confirm the data source is connected**

Go to Connections → Data sources → click your Prometheus data source → **Save & test**.
It must show: `Successfully queried the Prometheus API.`

If it does not, fix the data source first (see [section 4](#4-grafana-cannot-reach-prometheus--the-localhost-trap)).

**Step 2: Check the time range**

The time picker is in the top-right corner of the dashboard. A common mistake is leaving
it at a time range from before any data existed. Set it to `Last 15 minutes` or `Last 1 hour`.

```
Top-right of every Grafana dashboard:
  [Last 15 minutes ▾]   [🔄 auto ▾]   [🔄]
```

Click the dropdown and select `Last 15 minutes`.

**Step 3: Has Prometheus collected any data yet?**

Prometheus scrapes every 15 seconds (or 5 seconds in the demo project). On a fresh start
you may need to wait 30–60 seconds before any time-series data exists.

Run the PromQL query directly in the Prometheus UI first:

1. Open `http://localhost:9090`
2. Type `up` and press Execute
3. If you see results, data exists and the problem is in Grafana's query or time range
4. If `up` returns nothing, Prometheus has not scraped yet — wait and retry

**Step 4: Test the PromQL query in Grafana Explore**

1. Click the compass icon (Explore) in the left sidebar
2. Select `Prometheus` as the data source
3. Paste the query from the broken panel (e.g. `sum(rate(http_requests_total[1m]))`)
4. Click Run query

If Explore shows data but the dashboard does not, the panel's time range or refresh
settings are misconfigured. Open the panel editor and check the time range override.

**Step 5: `rate()` requires at least two scrapes**

The `rate()` function calculates the per-second increase of a counter. It needs at
least **two data points** within the time window. If you just started the stack, the
`[1m]` window may not have two scrapes yet.

Wait 30–60 seconds and refresh. Or temporarily change `[1m]` to `[2m]` in the query
to give a wider window.

**Step 6: Check for "No data" vs NaN**

- **No data** — Prometheus has no time-series matching the metric name and labels
- **NaN** — the query returned a value but it cannot be computed (e.g. `0/0` for an
  error rate when there are no requests)

Both are normal on fresh stacks. Generate some traffic to the running project:
```bash
# Flask Web API (project 1):
for i in $(seq 1 10); do curl -s http://localhost:8081/ > /dev/null; sleep 0.5; done

# Job Processor (project 2):
for i in $(seq 1 10); do curl -s -X POST http://localhost:8082/jobs \
  -H "Content-Type: application/json" -d '{}' > /dev/null; sleep 0.5; done
```

Then refresh the dashboard.

---

## 7. Provisioned data source or dashboard not appearing

### Symptom

After `docker compose up -d`, you expect Grafana to already have the Prometheus data
source and a dashboard, but the data sources list is empty or the dashboard folder is missing.

### Cause 1: Wrong working directory for docker compose up

Provisioning works via bind-mounted directories. If the paths in `docker-compose.yml`
resolve incorrectly, the container starts with empty provisioning directories.

**Fix:** Always run `docker compose up -d` from the directory that *contains*
`docker-compose.yml`. Do not run it from a parent directory.

```bash
# Wrong:
cd /home/user/repos/monitoring-observability
docker compose up -d   # reads wrong docker-compose.yml or none

# Correct:
cd /home/user/repos/monitoring-observability/integration
docker compose up -d
```

### Cause 2: Grafana started before provisioning files were mounted

Verify the bind mounts resolved correctly:

```bash
# List what's actually inside the provisioning directory in the container:
docker exec grafana ls /etc/grafana/provisioning/datasources/
docker exec grafana ls /etc/grafana/provisioning/dashboards/
docker exec grafana ls /var/lib/grafana/dashboards/
```

Expected output for `datasources/`: `prometheus.yml`

If those directories are empty, the bind mount paths in `docker-compose.yml` are wrong.
Check the exact paths and make sure they exist on your machine.

### Cause 3: Provisioning file has a syntax error

Grafana silently skips provisioning files it cannot parse. Check the logs:

```bash
docker compose logs grafana | grep -i "provision\|error\|warn"
```

Look for lines like:
```
msg="Failed to load provisioning config file" filename=prometheus.yml err="..."
```

Open the provisioning YAML file and look for indentation errors or missing fields.

### Cause 4: Named volume retains old Grafana state from a previous run

If you ran Grafana before (without `-v`), the named volume may have cached state that
conflicts with new provisioning.

**Fix:**
```bash
docker compose down -v   # -v removes the named volumes
docker compose up -d
```

### Verify provisioning worked via the API

```bash
# List data sources:
curl -s -u admin:admin http://localhost:3000/api/datasources

# List dashboards:
curl -s -u admin:admin "http://localhost:3000/api/search?type=dash-db"
```

---

## 8. Config file not found — bind mount failures

### Error message

In container logs:

```
msg="Error loading config" err="open /etc/prometheus/prometheus.yml: no such file or directory"
```

Or when running `docker run`:
```
docker: Error response from daemon: invalid mount config for type "bind":
bind source path does not exist: /nonexistent/path/prometheus.yml
```

### Root cause

When mounting a file or directory into a container (`-v` or `volumes:` in Compose),
Docker resolves the source path on your machine at the moment the container starts.
If that path does not exist, Docker either errors out or mounts an empty location.

### Diagnosis

**Check that the file exists where Docker expects it:**
```bash
# If using docker run with $(pwd):
echo $(pwd)   # make sure this is the prometheus-setup/ directory

# List the files in the current directory:
ls -la prometheus.yml

# Check what path Docker resolved the mount to:
docker inspect prometheus --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
```

### Fix: Run from the correct directory

Every `docker run` command in this repo uses `$(pwd)/prometheus.yml` as a relative path.
This means the command **must be run from the directory that contains `prometheus.yml`**.

```bash
# Wrong — running from the repo root:
cd /home/user/repos/monitoring-observability
docker run ... -v "$(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml" ...
# This tries to mount /home/user/repos/monitoring-observability/prometheus.yml
# which does not exist.

# Correct:
cd /home/user/repos/monitoring-observability/prometheus-setup
docker run ... -v "$(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml" ...
# This mounts /home/user/repos/monitoring-observability/prometheus-setup/prometheus.yml ✓
```

### WSL2 users: Windows path in $(pwd)

If your terminal is a Windows PowerShell session (not WSL2 bash), `$(pwd)` returns a
Windows path like `C:\Users\...`. Docker on WSL2 needs a Unix-style path.

**Fix:** Run all commands from the WSL2 Ubuntu terminal, not from PowerShell.

To open WSL2 Ubuntu: press Win+R → type `wsl` → Enter.

---

## 9. Volume permission errors — Grafana cannot write

### Error message

In Grafana container logs:

```
GF_PATHS_DATA='/var/lib/grafana' is not writable.
You may have issues with file permissions, more information here: http://docs.grafana.org/installation/docker/#migrate-to-v51-or-later
```

Or:

```
mkdir: can't create directory '/var/lib/grafana/plugins': Permission denied
```

### Root cause

The official Grafana Docker image runs as **UID 472** (a non-root user called `grafana`).
When you bind-mount a host directory, Docker creates it with root ownership. UID 472
cannot write to a root-owned directory, so Grafana cannot initialize its database.

### Why this does not happen with named volumes

Named volumes (`grafdata:/var/lib/grafana`) are initialized by Docker with correct
ownership before the container starts. They are the correct approach.

### Fix A: Use a named volume (recommended)

In `docker-compose.yml`:
```yaml
volumes:
  - grafdata:/var/lib/grafana   # correct — named volume

# NOT:
# - ./grafana-data:/var/lib/grafana   # this causes the permission error
```

At the bottom of the same file:
```yaml
volumes:
  grafdata:
```

### Fix B: Fix ownership on the host directory

If you specifically need a host-directory mount (e.g. to access the files directly
from your machine), set the ownership before starting the container:

```bash
# Create the directory and give it to UID 472:
mkdir -p ./grafana-data
sudo chown -R 472:472 ./grafana-data
```

Then start the container — Grafana can now write to it.

---

## 10. Python project image fails to build

### Symptom

`docker compose up -d --build` fails with a build error.

### Error: pip cannot resolve packages (network issue)

```
#5 [3/4] RUN pip install --no-cache-dir -r requirements.txt
#5 ERROR: Could not find a version that satisfies the requirement flask==3.0.3
#5 ERROR: No matching distribution found for flask==3.0.3
```

Or a network error:
```
#5 ERROR: Could not fetch URL https://pypi.org/simple/flask/
    There was a problem confirming the ssl certificate: ...
    (Caused by NewConnectionError: Failed to establish a new connection)
```

**Cause:** The Docker build environment cannot reach the internet (PyPI).

**Fix:**
1. Check your connection: `curl https://pypi.org` from your terminal.
2. On WSL2: make sure Docker Desktop is running (not just WSL2).
3. Behind a corporate proxy: configure Docker daemon proxy settings.

### Error: Dockerfile not found

```
ERROR [internal] load build definition from Dockerfile
Dockerfile: no such file or directory
```

**Cause:** `docker compose up` is being run from the wrong directory. The `build: ./app`
path in each project's `docker-compose.yml` is relative to that file's location.

**Fix:** Run from the project root directory (the one containing `docker-compose.yml`):
```bash
cd projects/01-flask-web-api
docker compose up -d --build

# NOT from repo root:
# docker compose -f projects/01-flask-web-api/docker-compose.yml up -d --build
# (this would resolve ./app relative to your shell's cwd, not the compose file)
```

### Error: Code changes not reflected after rebuild

If you edited `app/app.py` but the running container still shows old behaviour:

```bash
# Force rebuild with no layer cache:
docker compose build --no-cache
docker compose up -d
```

Or in one command:
```bash
docker compose up -d --build --force-recreate
```

### Checking what is inside the built image

```bash
# Open a shell inside the built image to inspect files:
docker run --rm -it 01-flask-web-api-flask-web-api sh
ls -la /app
cat /app/app.py

# Same pattern for the other projects:
docker run --rm -it 02-job-processor-job-processor sh
docker run --rm -it 03-cache-service-cache-service sh
```

---

## 11. YAML syntax errors in prometheus.yml or docker-compose.yml

YAML is indentation-sensitive. A single wrong tab or space causes a parse failure that
is often hard to read.

### Common mistakes

**Using tabs instead of spaces:**

YAML does not allow tab characters for indentation — only spaces.
Most text editors show this differently; set your editor to "expand tabs to spaces."

```yaml
# Wrong (tab character before targets):
  static_configs:
	- targets:       # ← this is a tab, not spaces

# Correct (spaces):
  static_configs:
    - targets:       # ← two spaces + two spaces = four spaces total
```

**Missing space after the colon:**

```yaml
# Wrong:
job_name:"prometheus"

# Correct:
job_name: "prometheus"
```

**Incorrect list syntax:**

```yaml
# Wrong — dashes need a space after them:
targets:
  -"localhost:9090"

# Correct:
targets:
  - "localhost:9090"
```

**Wrong indentation depth:**

```yaml
# Wrong — targets is at the same level as static_configs:
scrape_configs:
  - job_name: "prometheus"
  static_configs:        # ← should be indented under the job
    - targets: ["localhost:9090"]

# Correct:
scrape_configs:
  - job_name: "prometheus"
    static_configs:      # ← indented 4 spaces under scrape_configs list item
      - targets: ["localhost:9090"]
```

### Validate before running

```bash
# Validate prometheus.yml using promtool, which ships inside the Prometheus image.
# The image's default entrypoint is /bin/prometheus, so override it with --entrypoint
# to run promtool instead:
docker run --rm \
  -v "$(pwd)/prometheus.yml:/etc/prometheus/prometheus.yml:ro" \
  --entrypoint promtool \
  prom/prometheus:v3.12.0 \
  check config /etc/prometheus/prometheus.yml

# Validate docker-compose.yml:
docker compose config
```

`promtool check config` prints a `SUCCESS:` line and exits 0 if the file is valid, for example:
```
Checking /etc/prometheus/prometheus.yml
 SUCCESS: 0 rule files found
```
If the file is invalid it prints `FAILED:` with the parse error and exits non-zero.
`docker compose config` dumps the resolved config — if it prints without error, the
YAML is valid.

> **Why not `prometheus --check-config`?** The `prometheus` binary has no such flag —
> config validation lives in the separate `promtool` tool. Passing `--check-config` to
> Prometheus just errors with "unknown flag".

### Read the parse error carefully

Prometheus YAML errors include line numbers:

```
msg="Error loading config" err="parsing YAML file /etc/prometheus/prometheus.yml:
yaml: line 14: did not find expected key"
```

Open the file, go to line 14, and look at the indentation and syntax there and on the
two lines above it (the error is often on the preceding line).

---

## 12. docker-compose command not found


### Error

```
bash: docker-compose: command not found
```

Or on Windows:

```
'docker-compose' is not recognized as an internal or external command
```

### Cause

Docker Compose v2 is built into Docker Desktop as a plugin. It is invoked as
`docker compose` (two words, space). The old standalone `docker-compose` binary (v1)
is deprecated and is no longer bundled.

### Fix

Replace `docker-compose` with `docker compose` everywhere:

```bash
# Old (v1, deprecated):
docker-compose up -d
docker-compose down

# New (v2, correct):
docker compose up -d
docker compose down
```

All commands in this repository use the v2 syntax.

**Verify your version:**
```bash
docker compose version
# Expected: Docker Compose version v2.x.x
```

If `docker compose version` returns an error, Docker is not installed correctly.
Return to `docs/wsl-setup.md` and verify the installation steps.

---

## 13. WSL2-specific path issues

### Problem: $(pwd) returns a Windows path

If you open a Windows terminal (PowerShell, CMD) and type `wsl`, you may be in a mixed
environment where `$(pwd)` returns something unexpected.

**Check where you are:**
```bash
pwd
```

If the output starts with `/mnt/c/...`, you are working on a Windows path inside WSL2.
This works but can be slow and cause path resolution issues with Docker.

**Better approach:** Work in your WSL2 home directory:
```bash
cd ~
git clone <repo-url> monitoring-observability
cd monitoring-observability
```

The home directory (`~`) is at `/home/username` inside WSL2 — a native Linux filesystem
path. Docker Desktop handles this correctly.

### Problem: Line endings (CRLF vs LF)

If you cloned this repository on Windows and your `git config` is set to convert line
endings, config files may have Windows-style line endings (`\r\n`).
Some tools inside Linux containers do not handle `\r\n` well.

**Check for CRLF in config files:**
```bash
file prometheus.yml
# If output includes "CRLF", the file has Windows line endings
```

**Fix:**
```bash
# Convert to LF:
sed -i 's/\r//' prometheus.yml

# Or configure git to not convert line endings:
git config --global core.autocrlf false
git checkout -- .
```

### Problem: Docker Desktop WSL2 integration not enabled

If `docker` commands work in PowerShell but not in the WSL2 Ubuntu terminal:

1. Open Docker Desktop → Settings → Resources → WSL Integration
2. Enable the toggle for your Ubuntu distribution
3. Click Apply & Restart
4. Close and reopen the Ubuntu terminal (the WSL session needs to refresh)

---

## 14. External network "monitoring" not found

This error only occurs with the `infra/` + projects architecture (sections 5–8 of the
learning path). It does not apply to `prometheus-setup/`, `grafana-setup/`, or `integration/`.

### Error message

When running `docker compose up -d` in any project directory:

```
network monitoring declared as external, but could not be found
```

### Root cause

Each project's `docker-compose.yml` contains:

```yaml
networks:
  monitoring:
    external: true
```

`external: true` means: **join a network that already exists — do not create it.**
If the `monitoring` network does not exist yet, Docker refuses to start the container.

The `monitoring` network is created by `infra/docker-compose.yml`. If infra is not
running, or was started from the wrong directory, the network will not exist.

### Diagnosis

```bash
# Does the network exist?
docker network ls | grep monitoring
```

If the output is empty, the network does not exist.

```bash
# What networks do exist?
docker network ls
```

You may see `infra_monitoring` instead of `monitoring`. This means infra was started
but the network got the wrong name — see the fix below.

### Fix A: Start infra first (the usual fix)

```bash
cd infra
docker compose up -d
```

Then verify:
```bash
docker network ls | grep monitoring
```

Expected output:
```
xxxxxxxxxx   monitoring   bridge    local
```

Now go back to your project directory and retry `docker compose up -d --build`.

### Fix B: Network exists as "infra_monitoring" instead of "monitoring"

This happens when `infra/docker-compose.yml` does **not** have the `name:` field under
`networks:`. Without `name: monitoring`, Docker Compose prefixes the network name with
the project name (`infra`), producing `infra_monitoring`.

Open `infra/docker-compose.yml` and confirm the networks block looks like this:

```yaml
networks:
  monitoring:
    name: monitoring    # ← this line must be present
    driver: bridge
```

If the `name:` line is missing, add it, then:

```bash
cd infra
docker compose down      # removes the wrongly-named network
docker compose up -d     # recreates it with the correct name
```

### Fix C: You ran docker compose from the wrong directory

Each project's `docker-compose.yml` uses `external: true` to look up the network by
name. This lookup always uses the literal name `monitoring` regardless of which directory
you run from. As long as the network exists (from infra), running from any directory works.

```bash
# Verify from wherever you are:
docker network inspect monitoring
```

If this returns JSON with `"Name": "monitoring"`, the network is fine and the error
is something else — check `docker logs` for the actual container error.

---

## 15. How to read logs effectively

### Basic log commands

```bash
# Last N lines:
docker logs --tail 50 prometheus
docker logs --tail 100 grafana

# All logs since a time window:
docker logs --since 5m prometheus          # last 5 minutes
docker logs --since 2024-01-01T00:00:00Z prometheus

# Follow live (Ctrl+C to stop):
docker logs -f prometheus

# Timestamps on every line:
docker logs -t prometheus
```

### Via Docker Compose (run from the project directory)

```bash
# All services, last 20 lines each:
docker compose logs --tail 20

# One service:
docker compose logs prometheus

# Follow all services live:
docker compose logs -f

# Follow one service:
docker compose logs -f grafana
```

### What to look for

**Prometheus logs — healthy startup:**
```
ts=... caller=main.go level=info msg="Starting Prometheus" ...
ts=... caller=main.go level=info msg="Completed loading of configuration file" ...
ts=... caller=main.go level=info msg="Server is ready to receive web requests."
```

**Prometheus logs — scrape failure:**
```
ts=... caller=scrape.go level=warn msg="Error scraping target" ...
err="..."
```

**Grafana logs — healthy startup:**
```
logger=settings t=... msg="Starting Grafana" version=13.0.1
logger=server t=... msg="HTTP Server Listen" address=[::]:3000
```

**Grafana logs — provisioning:**
```
logger=provisioning.datasources msg="inserting datasource from configuration ..." name=Prometheus
logger=provisioning.dashboard msg="starting to provision dashboards"
```

**Grafana logs — provisioning error:**
```
logger=provisioning t=... level=error msg="Failed to load provisioning config file" ...
```

### Filtering logs with grep

```bash
# Only errors:
docker logs prometheus 2>&1 | grep -i "error\|warn\|fail"

# Scrape-related lines:
docker logs prometheus 2>&1 | grep -i "scrape"

# Provisioning lines in Grafana:
docker compose logs grafana 2>&1 | grep -i "provision"
```

---

## 16. Full reset — start from scratch

Use this when the environment is in an unknown or broken state and you want to begin
fresh.

### Reset one project

```bash
cd <project-directory>   # e.g. cd integration

# Stop and remove containers AND named volumes:
docker compose down -v

# Start fresh:
docker compose up -d
```

### Remove a specific container by name

```bash
docker rm -f prometheus
docker rm -f grafana
docker rm -f flask-web-api job-processor cache-service
```

### Reset specific project stacks

```bash
# infra (Prometheus + Grafana):
cd infra && docker compose down -v

# Individual projects:
cd projects/01-flask-web-api && docker compose down
cd projects/02-job-processor  && docker compose down
cd projects/03-cache-service  && docker compose down

# integration/ (standalone teaching section):
cd integration && docker compose down -v
```

### Remove specific volumes by name

```bash
docker volume rm infra_promdata infra_grafdata
docker volume rm integration_promdata integration_grafdata
```

### Remove the shared network

```bash
docker network rm monitoring
```

### Remove all stopped containers, unused networks, dangling images

```bash
docker system prune
```

Add `--volumes` to also remove all unused volumes:
```bash
docker system prune --volumes
```

> **Warning:** `docker system prune` affects all Docker projects on your machine,
> not just this repository. It removes anything Docker considers "unused."

### Verify the environment is clean

```bash
docker ps -a           # should be empty (or only containers you want)
docker network ls      # should only show bridge, host, none
docker volume ls       # should only show volumes you want to keep
```

After a full prune:
```bash
docker run hello-world   # confirm Docker itself still works
```

---

## 17. System monitors (Projects 4 and 6) show odd values

Run `scripts/validate-connectivity.sh system-monitor system-monitor:8084 system-monitor` (or the
`psutil-system-monitor` equivalent) first — it tells you whether this is a connectivity problem
or a values problem.

#### Memory / uptime match the container, not the host

**Cause:** the host `/proc` is not mounted, so the app reads the container's own `/proc`.

```bash
docker inspect system-monitor --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
```

**Expected:** `/proc -> /host/proc`. If missing, check the `volumes:` section of the project's
`docker-compose.yml` and recreate: `docker compose up -d --force-recreate`.

#### Numbers don't match Task Manager / Activity Monitor

**Expected behaviour on Docker Desktop.** Containers run inside a Linux VM, and the monitors
report that VM. On WSL2 compare with `free -h` and `uptime` *inside* WSL instead.

#### `host_disk_usage_percent` lists `/etc/hosts`, `/etc/resolv.conf`, …

**Cause:** `DISK_PATHS` is not set for Project 6, so psutil lists Docker's bind-mounted files as
partitions. Add `DISK_PATHS: "/"` under `environment:` in
`projects/06-psutil-system-monitor/docker-compose.yml` and run `docker compose up -d`.

#### Network panel only shows `eth0` and `lo`

**Expected.** `/proc/net` is per network namespace — the container sees only its own interfaces.
See `projects/06-psutil-system-monitor/README.md`.

---

## 18. Blackbox probes fail or show no data (Projects 7 and 8)

#### Target is UP on /targets but the dashboard shows it DOWN

**Not a contradiction.** For a probe job, `up` means "Prometheus reached the **exporter**".
Whether the probed service is healthy is `probe_success`. Ask the exporter why the probe failed:

```bash
curl -s 'http://localhost:9115/probe?module=http_2xx&target=http://cache-service:8083/stats&debug=true' \
  | sed -n '1,/Metrics that/p'
```

(Project 8 uses port **9116**.) The last log lines name the failing step: DNS resolution,
connection refused, status code, regex mismatch.

#### `lookup <name> on 127.0.0.11:53: no such host`

**Cause:** the probed container is not running or not on the `monitoring` network. Docker's DNS
only knows names of running containers on the same network.

```bash
docker ps --filter network=monitoring --format '{{.Names}}'
```

#### `Logs for the probe:` is empty in `debug=true` output

**Cause:** the exporter was started without `--log.prober=info`, so probe logs stay at debug
level. Both project `docker-compose.yml` files pass it — recreate with `docker compose up -d`.

#### Every target in a probe job is DOWN with `connection refused` / `no such host` on `blackbox-…:9115`

**Cause:** the exporter itself is down, or the `replacement:` in `relabel_configs` is wrong. It
must be the **container** name and port — `blackbox-http:9115` or `blackbox-network:9115` —
never `localhost` and never the host port `9116`.

```bash
docker exec prometheus wget -qO- http://blackbox-network:9115/-/healthy
```

#### All probes show `instance="blackbox-http:9115"`

**Cause:** the relabel steps are in the wrong order. `__param_target` and `instance` must be set
from `__address__` **before** `__address__` is overwritten with the exporter address. Copy the
block from `infra/prometheus.yml` exactly.

#### Probe fails with `unknown module` / HTTP 400

```
Unknown module "http2xx"
```

**Cause:** the `module` label in `prometheus.yml` doesn't match a name under `modules:` in
`blackbox.yml`. List what the exporter loaded:

```bash
curl -s http://localhost:9115/config
```

After editing `blackbox.yml`, restart the exporter (the file is bind-mounted, and editors often
replace the file rather than edit it in place):

```bash
docker compose restart blackbox-http        # or blackbox-network
```

#### ICMP probe fails with `socket: permission denied`

**Cause:** the exporter runs as a non-root user and the kernel is not allowing unprivileged ping
sockets. `projects/08-blackbox-network-probes/docker-compose.yml` sets
`net.ipv4.ping_group_range: "0 2147483647"`; check it is applied:

```bash
docker exec blackbox-network cat /proc/sys/net/ipv4/ping_group_range
```

**Expected:** `0	2147483647`.

#### `https_2xx_tls` / `dns_external` probes fail

**Expected without internet access** (or behind a proxy/firewall that blocks outbound 443 or
UDP 53). Everything else is on the local Docker network and keeps working.

---

## 19. Edited prometheus.yml but the reload changed nothing

### Symptom

`curl -X POST http://localhost:9090/-/reload` returns 200, but the new job never shows on
`http://localhost:9090/targets`.

### Diagnosis — does Prometheus see the file you saved?

```bash
docker exec prometheus grep -n 'job_name' /etc/prometheus/prometheus.yml
```

Compare with `grep -n 'job_name' infra/prometheus.yml` on your machine.

- **Container shows the old content** → the file is bind-mounted on its own and your editor
  saved by writing a new file and renaming it (vim, VS Code, sed -i and many others do). The
  mount still points at the old file. `infra/docker-compose.yml` avoids this by mounting the
  whole `infra/` directory; if you use an older copy with
  `./prometheus.yml:/etc/prometheus/prometheus.yml:ro`, either switch to `./:/etc/prometheus:ro`
  or restart after each edit:
  ```bash
  docker compose -f infra/docker-compose.yml up -d        # picks up a changed mount
  docker compose -f infra/docker-compose.yml restart prometheus
  ```
- **Container shows the new content** → the job is still commented, or the reload failed on a
  YAML error. Check both:
  ```bash
  docker exec prometheus promtool check config /etc/prometheus/prometheus.yml
  docker logs prometheus 2>&1 | grep -iE "reload|error loading" | tail -3
  ```
- **Job present but UNKNOWN** → wait for the first scrape (≤15 seconds).

