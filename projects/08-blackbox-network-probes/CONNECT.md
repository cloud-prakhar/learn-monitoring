# Connecting Blackbox Network Probes to Prometheus and Grafana

Follow these steps in order. Each one has a check so you know it worked before moving on.

---

## Before you start

```bash
cd infra
docker compose up -d
docker network ls | grep monitoring
```

The TCP and ICMP probes target Projects 1–6 and Project 7's exporter. Start whichever you want
covered (see [Project 7 CONNECT.md](../07-blackbox-http-probes/CONNECT.md) "Before you start"
for a loop that starts 1–6). Anything not running shows as a failed probe.

---

## Step 1 — Start the exporter

From `projects/08-blackbox-network-probes/`:

```bash
docker compose up -d
```

Expected:

```
 ✔ Container blackbox-network  Started
```

```bash
docker logs blackbox-network 2>&1 | grep -i "loaded config"
```

Expected: a line with `msg="Loaded config file"`.

---

## Step 2 — Run each kind of probe by hand

Use host port **9116**.

**TCP — open port vs closed port:**

```bash
curl -s 'http://localhost:9116/probe?module=tcp_connect&target=grafana:3000' | grep ^probe_success
curl -s 'http://localhost:9116/probe?module=tcp_connect&target=grafana:9999' | grep ^probe_success
```

```
probe_success 1
probe_success 0
```

**TCP with a conversation** — talk HTTP by hand over a raw socket:

```bash
curl -s 'http://localhost:9116/probe?module=tcp_grafana_http_banner&target=grafana:3000&debug=true' | grep -iE 'expect|match|succeeded'
```

```
... msg="Regexp matched" module=tcp_grafana_http_banner target=grafana:3000 regexp="^HTTP/1\\.[01] 200" line="HTTP/1.0 200 OK"
... msg="Probe succeeded" module=tcp_grafana_http_banner target=grafana:3000 duration_seconds=0.0023
```

The exporter sent the request over a plain TCP socket, read the first line back, and matched it.
(The probe log lines appear because `docker-compose.yml` passes `--log.prober=info`.)

**ICMP — ping a container by name:**

```bash
curl -s 'http://localhost:9116/probe?module=icmp_ping&target=prometheus' | grep -E '^probe_(success|icmp_duration_seconds)'
```

```
probe_icmp_duration_seconds{phase="resolve"} 0.0006
probe_icmp_duration_seconds{phase="rtt"} 0.0005
probe_icmp_duration_seconds{phase="setup"} 0.0001
probe_success 1
```

Round-trip under a millisecond — both containers sit on the same Docker bridge.

**DNS — a name that exists and one that doesn't:**

```bash
curl -s 'http://localhost:9116/probe?module=dns_container_prometheus&target=127.0.0.11:53' | grep -E '^probe_(success|dns_answer_rrs)'
curl -s 'http://localhost:9116/probe?module=dns_container_missing&target=127.0.0.11:53' | grep -E '^probe_(success|dns_answer_rrs|dns_query_succeeded)'
```

```
probe_dns_answer_rrs 1
probe_success 1

probe_dns_answer_rrs 0
probe_dns_query_succeeded 1
probe_success 0
```

The second probe *got an answer* (`probe_dns_query_succeeded 1`) — the answer was NXDOMAIN,
which `valid_rcodes: [NOERROR]` rejects.

**External DNS** (needs internet):

```bash
curl -s 'http://localhost:9116/probe?module=dns_external&target=1.1.1.1:53' | grep ^probe_success
```

---

## Step 3 — Add the probe jobs to Prometheus

In `infra/prometheus.yml`, uncomment the four Project 8 jobs — `blackbox-tcp`, `blackbox-icmp`,
`blackbox-dns`, `blackbox-exporter-network` — by removing the leading `# ` from every line of
their blocks. Each probe job ends with the same relabel block, pointing at the network exporter:

```yaml
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [module]
        target_label: __param_module
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: blackbox-network:9115     # container port, not 9116
```

Note `blackbox-network:9115`, not `9116`: 9116 is the port on **your machine**. Prometheus talks
container-to-container on the network, where the exporter listens on 9115.

```bash
docker exec prometheus promtool check config /etc/prometheus/prometheus.yml
curl -X POST http://localhost:9090/-/reload
```

---

## Step 4 — Validate connectivity

**4a. Prometheus → exporter on the container port:**

```bash
docker exec prometheus wget -qO- http://blackbox-network:9115/metrics | grep -c '^blackbox_'
```

Expected: a number above 0.

> Wait ~15 seconds after the reload for the first scrape — before that, targets are UNKNOWN
> and the checks below report them as not UP.

**4b. One command per job, from the repo root:**

```bash
scripts/validate-connectivity.sh blackbox-tcp blackbox-network:9115 blackbox-network
scripts/validate-connectivity.sh blackbox-icmp
scripts/validate-connectivity.sh blackbox-dns
scripts/validate-connectivity.sh blackbox-exporter-network blackbox-network:9115
```

Every run should end with `0 failed`. The probe summaries should read:

```
  info  probe_success: 10/11 probes passing
      probe failing: tcp_connect grafana:9999 (expected)
...
  info  probe_success: 6/6 probes passing
...
  info  probe_success: 3/4 probes passing
      probe failing: dns_container_missing 127.0.0.11:53 (expected)
```

Anything failing *without* `(expected)` is a real problem — usually a project that isn't running,
or no internet for `dns_external`.

**4c.** **http://localhost:9090/targets** — `blackbox-tcp (11/11 up)`, `blackbox-icmp (6/6 up)`,
`blackbox-dns (4/4 up)`. Remember: UP = the exporter answered, not that the probe passed.

---

## Step 5 — Explore in Prometheus

| Query | What it shows |
|-------|--------------|
| `probe_success{job="blackbox-tcp"}` | Port open (1) / closed (0) |
| `probe_success{expected!="down"} == 0` | Only *unexpected* failures — the alert you'd write |
| `probe_icmp_duration_seconds{phase="rtt"}` | Ping round-trip per container |
| `probe_dns_answer_rrs{job="blackbox-dns"}` | Answer records per DNS check |
| `probe_duration_seconds{job="blackbox-dns"}` | DNS query time per server |

---

## Step 6 — Break things and read the layers

Stop a container and see which layers fail:

```bash
docker stop system-monitor
```

After one scrape (≤15s):

```bash
curl -s http://localhost:9090/api/v1/query --data-urlencode \
  'query=probe_success{instance=~"(http://)?system-monitor(:8084)?/?"}' \
  | python3 -c 'import json,sys; [print(r["metric"]["job"], r["metric"]["module"], r["metric"]["instance"], r["value"][1]) for r in json.load(sys.stdin)["data"]["result"]]'
```

```
blackbox-tcp tcp_connect system-monitor:8084 0
blackbox-icmp icmp_ping system-monitor 0
blackbox-http http_2xx http://system-monitor:8084/ 0        ← if Project 7 is running
blackbox-http http_body_ok http://system-monitor:8084/ 0
```

Everything fails at once because a stopped container also disappears from Docker DNS — the
debug log shows the real cause:

```bash
curl -s 'http://localhost:9116/probe?module=icmp_ping&target=system-monitor&debug=true' | grep -i 'resol'
```

```
... msg="Error resolving address" module=icmp_ping target=system-monitor err="lookup system-monitor on 127.0.0.11:53: no such host"
```

Now compare a process that is **up but not listening**: `grafana:9999` fails TCP while
`icmp_ping` to `grafana` passes. That combination means "host fine, nothing on that port".

```bash
docker start system-monitor
```

---

## Step 7 — Open the Grafana dashboard

**http://localhost:3000** → Dashboards → Projects → **Blackbox Network Probes** (provisioned by
`infra/`). To import by hand: Dashboards → New → Import →
`projects/08-blackbox-network-probes/dashboards/blackbox-network.json`.

| Panel | Shows |
|---|---|
| TCP Ports Open / Hosts Answering Ping / DNS Checks Passing | Passing probes per type (expected-down excluded) |
| Unexpected Failures | Should be **0** |
| Expected-Down Still Down | Should be **2** (`grafana:9999`, `no-such-service`) |
| Exporter Scrape | `up` of the network exporter |
| TCP Port Checks / ICMP Ping / DNS Checks | State timelines, green UP / red DOWN |
| ICMP Round-Trip Time, TCP and DNS Probe Duration | Latency per target |
| DNS Answers | Table: server, module, up, answer records, duration |

---

## Clean up

See **[CLEANUP.md](CLEANUP.md)**.
