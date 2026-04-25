#!/usr/bin/env bash
# Rebuild + restart just the backend container after code changes.
set -eu

cd /mnt/ssd/adsb

echo "=== Rebuild adsb-backend image ==="
docker compose build adsb-backend

echo ""
echo "=== Restart container ==="
docker compose up -d adsb-backend

echo ""
echo "=== Wait 8s and tail logs ==="
sleep 8
docker compose logs --tail=30 adsb-backend

echo ""
echo "=== Quick probe ==="
curl -fsS http://localhost:8000/api/stats/live | jq '{messages_per_sec, aircraft_total, aircraft_with_position}'
