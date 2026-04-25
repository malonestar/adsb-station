#!/usr/bin/env bash
# Nuke the SQLite DB, re-run migrations, rebuild and restart backend.
# Safe to run during Plan 2a iteration when the DB has no real data yet.
set -eu

cd /mnt/ssd/adsb

echo "=== Stop adsb-backend ==="
docker compose stop adsb-backend

echo "=== Delete DB + WAL + SHM files ==="
rm -f /mnt/ssd/data/db/adsb.db /mnt/ssd/data/db/adsb.db-wal /mnt/ssd/data/db/adsb.db-shm
ls -la /mnt/ssd/data/db/

echo "=== Rebuild backend image ==="
docker compose build adsb-backend

echo "=== Run migration on empty DB ==="
docker compose run --rm adsb-backend alembic upgrade head

echo "=== Verify schema ==="
docker run --rm -v /mnt/ssd/data/db:/data/db python:3.13-slim \
  python -c "import sqlite3; c=sqlite3.connect('/data/db/adsb.db'); print([r[0] for r in c.execute('SELECT name FROM sqlite_master WHERE type=\"table\"')])"

echo "=== Bring up backend ==="
docker compose up -d adsb-backend

echo "=== Wait 10s and check logs ==="
sleep 10
docker compose logs --tail=30 adsb-backend 2>&1 | grep -iE 'error|exception|startup|flushed' || echo "(no matches)"

echo ""
echo "=== Stats probe ==="
curl -fsS http://localhost:8000/api/stats/live | jq '{messages_per_sec, aircraft_total, aircraft_with_position, max_range_nm_today}'
