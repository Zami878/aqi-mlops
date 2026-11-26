#!/usr/bin/env sh
# Smoke test a running API container: ./deploy/smoke.sh <base_url> <expected_git_sha>
set -eu
BASE=${1:-http://localhost:8000}
SHA=${2:-}

for i in $(seq 1 30); do
  curl -fsS "$BASE/health" >/dev/null 2>&1 && break
  [ "$i" = 30 ] && { echo "API did not become healthy"; exit 1; }
  sleep 1
done

curl -fsS "$BASE/health" | grep -q '"ok"'
[ -z "$SHA" ] || curl -fsS "$BASE/version" | grep -q "$SHA"
FORECAST=$(curl -fsS "$BASE/forecast")
echo "forecast: $FORECAST"
echo "$FORECAST" | python3 -c "import json,sys; d=json.load(sys.stdin); assert 0 <= d['aqi'] <= 500, d"
curl -fsS "$BASE/metrics" | grep -q '^aqi_forecast '
echo "smoke test passed"
