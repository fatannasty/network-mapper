#!/bin/bash
# Pre-warm the demo caches so key pages paint instantly.
# Run this ~1 minute before presenting (the caches have a 60s TTL), or between
# demo sections. Idempotent and safe.
#
#   ./scripts/prewarm.sh            # warm defaults
#   ./scripts/prewarm.sh "Site A" "Site B"   # also warm specific site topologies

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="http://localhost:8000"
FRONT="http://localhost:5173"

set -e
echo ">> checking servers..."
curl -s -m 8 "$API/health" >/dev/null || { echo "backend not up — run: nm-up"; exit 1; }
curl -s -m 8 -o /dev/null "$FRONT/" || { echo "frontend not up — run: nm-up"; exit 1; }

TOKEN="$(curl -s -m 10 -X POST "$API/api/auth/login" -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")"
AUTH="Authorization: Bearer $TOKEN"

warm() {
  local name="$1" url="$2"
  local t0 t1 ms
  t0=$(date +%s%N)
  curl -s -m 30 -o /dev/null -H "$AUTH" "$url"
  t1=$(date +%s%N)
  ms=$(( (t1 - t0) / 1000000 ))
  echo "   warm: $name  (${ms} ms)"
}

echo ">> warming caches..."
warm "executive health"   "$API/api/health/exec"
warm "inventory report"   "$API/api/inventory/report"
warm "topology (default)" "$API/api/topology"
warm "devices list"       "$API/api/inventory/devices?limit=5000"
warm "inventory links"    "$API/api/inventory/links"
for site in "$@"; do
  warm "topology: $site"  "$API/api/topology?site=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$site")"
done

echo ">> done. Demo path is warm."
echo "   tip: re-run nm-demo right before presenting or between sections (60s TTL)."