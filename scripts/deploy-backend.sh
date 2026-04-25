#!/usr/bin/env bash
# Deploy Plan 2a (backend) on the Pi.
# Run this from /mnt/ssd/adsb after scp'ing the backend/ directory.

set -eu

cd /mnt/ssd/adsb

echo "=== 1. Ensure /data/db exists on SSD ==="
mkdir -p /mnt/ssd/data/db
ls -la /mnt/ssd/data/db

echo ""
echo "=== 2. Build backend image ==="
docker compose build adsb-backend

echo ""
echo "=== 3. Run initial migrations (creates adsb.db with all tables) ==="
docker compose run --rm adsb-backend alembic upgrade head

echo ""
echo "=== 4. Verify schema ==="
docker run --rm -v /mnt/ssd/data/db:/data/db python:3.13-slim bash -c \
  "pip install --quiet sqlite-utils && python -c 'import sqlite3; c=sqlite3.connect(\"/data/db/adsb.db\"); print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type=\\\"table\\\"\")])'"

echo ""
echo "=== 5. Bring up the whole stack ==="
docker compose up -d
docker compose ps

echo ""
echo "=== 6. Wait 10s for backend to warm up, then probe endpoints ==="
sleep 10

echo ""
echo "--- /healthz ---"
curl -fsS http://localhost:8000/healthz | jq .

echo ""
echo "--- /readyz ---"
curl -fsS http://localhost:8000/readyz | jq .

echo ""
echo "--- /api/receiver ---"
curl -fsS http://localhost:8000/api/receiver | jq .

echo ""
echo "--- /api/aircraft/live (counts only) ---"
curl -fsS http://localhost:8000/api/aircraft/live | jq '{tick_count, aircraft_count: (.aircraft | length), last_tick}'

echo ""
echo "--- /api/stats/live ---"
curl -fsS http://localhost:8000/api/stats/live | jq '{messages_per_sec, aircraft_total, aircraft_with_position, max_range_nm_today}'

echo ""
echo "--- /api/feeds/health ---"
curl -fsS http://localhost:8000/api/feeds/health | jq '.feeds[] | {name, state}'

echo ""
echo "--- /api/alerts/live ---"
curl -fsS http://localhost:8000/api/alerts/live | jq '.alerts | length'

echo ""
echo "--- recent backend logs ---"
docker compose logs --tail=40 adsb-backend

echo ""
echo "=== Done. Next: commit the changes and deploy Plan 2b (frontend). ==="
