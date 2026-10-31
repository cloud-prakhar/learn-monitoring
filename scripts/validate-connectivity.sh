#!/usr/bin/env bash
# validate-connectivity.sh — check every hop between a project and Grafana.
#
#   app container ──► monitoring network ──► Prometheus scrape ──► Grafana data source ──► dashboard
#
# Usage:
#   scripts/validate-connectivity.sh <job> [container:port] [dashboard-uid]
#
# Examples:
#   scripts/validate-connectivity.sh system-monitor system-monitor:8084 system-monitor
#   scripts/validate-connectivity.sh blackbox-http blackbox-http:9115 blackbox-http
#   scripts/validate-connectivity.sh blackbox-dns                       # just the Prometheus side
#
# Needs: docker, curl, python3. Assumes the infra/ stack (prometheus + grafana) and the
# default Grafana login admin/admin. Override with PROM_URL, GRAFANA_URL, GRAFANA_AUTH.

set -u

JOB="${1:?usage: $0 <job> [container:port] [dashboard-uid]}"
APP="${2:-}"
DASH_UID="${3:-}"

PROM_URL="${PROM_URL:-http://localhost:9090}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"
GRAFANA_AUTH="${GRAFANA_AUTH:-admin:admin}"

PASS=0
FAIL=0
ok()   { echo "  PASS  $*"; PASS=$((PASS + 1)); }
bad()  { echo "  FAIL  $*"; FAIL=$((FAIL + 1)); }
info() { echo "  info  $*"; }

# Read JSON on stdin and print the result of a Python expression over it (bound to d).
jq_py() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)" 2>/dev/null; }

urlencode() { python3 -c "import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))" "$1"; }

echo "== Validating job '${JOB}'"

# 1. Shared network and the two infra containers -------------------------------------------
echo "-- Docker"
if docker network inspect monitoring >/dev/null 2>&1; then
  ok "network 'monitoring' exists"
else
  bad "network 'monitoring' missing — start infra/: cd infra && docker compose up -d"
fi

for c in prometheus grafana; do
  if [ "$(docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null)" = "true" ]; then
    ok "container '$c' is running"
  else
    bad "container '$c' is not running"
  fi
done

# 2. The app container: running, on the network, reachable FROM Prometheus -----------------
if [ -n "$APP" ]; then
  NAME="${APP%%:*}"
  if [ "$(docker inspect -f '{{.State.Running}}' "$NAME" 2>/dev/null)" = "true" ]; then
    ok "container '$NAME' is running"
  else
    bad "container '$NAME' is not running"
  fi

  NETS="$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$NAME" 2>/dev/null)"
  case " $NETS " in
    *" monitoring "*) ok "'$NAME' is attached to 'monitoring'" ;;
    *)                bad "'$NAME' is NOT on 'monitoring' (networks: ${NETS:-none})" ;;
  esac

  # Same path Prometheus uses: container DNS name + internal port, from inside the prometheus container.
  if docker exec prometheus wget -q -T 5 -O /dev/null "http://${APP}/metrics" 2>/dev/null; then
    ok "prometheus container can fetch http://${APP}/metrics"
  else
    bad "prometheus container cannot fetch http://${APP}/metrics (DNS or port problem)"
  fi
fi

# 3. Prometheus side: is the job configured, and are its targets UP? -----------------------
echo "-- Prometheus"
TARGETS_JSON="$(curl -s "${PROM_URL}/api/v1/targets?state=active")"
if [ -z "$TARGETS_JSON" ]; then
  bad "Prometheus API not reachable at ${PROM_URL}"
else
  SUMMARY="$(echo "$TARGETS_JSON" | JOB="$JOB" python3 -c '
import json, os, sys
job = os.environ["JOB"]
ts = [t for t in json.load(sys.stdin)["data"]["activeTargets"] if t["labels"].get("job") == job]
up = [t for t in ts if t["health"] == "up"]
print(len(ts), len(up))
for t in ts:
    if t["health"] != "up":
        print("DOWN", t["labels"].get("instance"), t.get("lastError", ""))
' 2>/dev/null)"
  TOTAL="$(echo "$SUMMARY" | head -1 | cut -d' ' -f1)"
  UP="$(echo "$SUMMARY" | head -1 | cut -d' ' -f2)"
  if [ "${TOTAL:-0}" = "0" ]; then
    bad "no active targets for job '${JOB}' — is the job uncommented in infra/prometheus.yml and Prometheus reloaded?"
  elif [ "$TOTAL" = "$UP" ]; then
    ok "all ${TOTAL} target(s) for job '${JOB}' are UP"
  else
    bad "${UP}/${TOTAL} target(s) UP for job '${JOB}'"
    echo "$SUMMARY" | tail -n +2 | sed 's/^/        /'
  fi
fi

Q="$(urlencode "up{job=\"${JOB}\"}")"
SERIES="$(curl -s "${PROM_URL}/api/v1/query?query=${Q}" | jq_py 'len(d["data"]["result"])')"
if [ "${SERIES:-0}" -gt 0 ] 2>/dev/null; then
  ok "query up{job=\"${JOB}\"} returns ${SERIES} series"
else
  bad "query up{job=\"${JOB}\"} returned no data yet (wait one scrape interval, 15s)"
fi

# Probe jobs: 'up' only proves the EXPORTER answered. probe_success is the probe result.
PQ="$(urlencode "probe_success{job=\"${JOB}\"}")"
PROBES="$(curl -s "${PROM_URL}/api/v1/query?query=${PQ}" | python3 -c '
import json, sys
r = json.load(sys.stdin)["data"]["result"]
if r:
    good = sum(1 for s in r if s["value"][1] == "1")
    print(good, len(r))
    for s in r:
        if s["value"][1] != "1":
            m = s["metric"]
            print("    probe failing:", m.get("module", "?"), m.get("instance", "?"),
                  "(expected)" if m.get("expected") == "down" else "")
' 2>/dev/null)"
if [ -n "$PROBES" ]; then
  info "probe_success: $(echo "$PROBES" | head -1 | awk '{print $1 "/" $2}') probes passing"
  echo "$PROBES" | tail -n +2 | sed 's/^/  /'
fi

# 4. Grafana side: data source health, query through Grafana, dashboard present ------------
echo "-- Grafana"
HEALTH="$(curl -s -o /dev/null -w '%{http_code}' "${GRAFANA_URL}/api/health")"
if [ "$HEALTH" = "200" ]; then ok "Grafana API is up"; else bad "Grafana API not reachable (HTTP ${HEALTH})"; fi

DS_UID="$(curl -s -u "$GRAFANA_AUTH" "${GRAFANA_URL}/api/datasources/name/Prometheus" | jq_py 'd["uid"]')"
if [ -z "$DS_UID" ]; then
  bad "Grafana data source 'Prometheus' not found (or login ${GRAFANA_AUTH%%:*} failed)"
else
  DS_STATUS="$(curl -s -u "$GRAFANA_AUTH" "${GRAFANA_URL}/api/datasources/uid/${DS_UID}/health" | jq_py 'd.get("status")')"
  if [ "$DS_STATUS" = "OK" ]; then
    ok "Grafana → Prometheus data source health is OK"
  else
    bad "Grafana → Prometheus data source health: ${DS_STATUS:-no answer}"
  fi

  GSERIES="$(curl -s -u "$GRAFANA_AUTH" \
    "${GRAFANA_URL}/api/datasources/proxy/uid/${DS_UID}/api/v1/query?query=${Q}" | jq_py 'len(d["data"]["result"])')"
  if [ "${GSERIES:-0}" -gt 0 ] 2>/dev/null; then
    ok "Grafana can query job '${JOB}' through the data source (${GSERIES} series)"
  else
    bad "Grafana returned no data for up{job=\"${JOB}\"}"
  fi
fi

if [ -n "$DASH_UID" ]; then
  TITLE="$(curl -s -u "$GRAFANA_AUTH" "${GRAFANA_URL}/api/dashboards/uid/${DASH_UID}" | jq_py 'd["dashboard"]["title"]')"
  if [ -n "$TITLE" ]; then
    ok "dashboard '${TITLE}' is loaded (${GRAFANA_URL}/d/${DASH_UID})"
  else
    bad "dashboard uid '${DASH_UID}' not found — provisioned from infra/grafana/dashboards/ or import it"
  fi
fi

echo "== ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
