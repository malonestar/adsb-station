#!/usr/bin/env bash
# Deploy Plan 2b (frontend) on the Pi.
# Builds the nginx+Vite image, updates the compose stack so nginx takes port 80.
set -eu

cd /mnt/ssd/adsb

echo "=== 1. Check frontend source is present ==="
ls -la frontend/ | head -20
[ -f frontend/package.json ] || { echo "FATAL: frontend/package.json missing — did scp finish?"; exit 1; }

echo ""
echo "=== 2. Build adsb-frontend image (will take 2-4 min on first build) ==="
docker compose build adsb-frontend

echo ""
echo "=== 3. Bring up the full stack (ultrafeeder + backend + frontend) ==="
docker compose up -d
docker compose ps

echo ""
echo "=== 4. Wait 10s for nginx to start ==="
sleep 10

echo ""
echo "=== 5. Probes ==="
echo "--- nginx /healthz ---"
curl -fsS http://localhost/healthz
echo ""

echo "--- SPA index.html head ---"
curl -sf http://localhost/ | head -5

echo ""
echo "--- /api/receiver via nginx proxy ---"
curl -fsS http://localhost/api/receiver | jq .

echo ""
echo "--- /api/stats/live via nginx proxy ---"
curl -fsS http://localhost/api/stats/live | jq '{messages_per_sec, aircraft_total, aircraft_with_position}'

echo ""
echo "--- /tar1090/data/aircraft.json via nginx proxy (fallback for power users) ---"
curl -fsS http://localhost/tar1090/data/aircraft.json | jq '.aircraft | length'

echo ""
echo "=== 6. Recent logs (frontend + backend + ultrafeeder) ==="
docker compose logs --tail=15 adsb-frontend adsb-backend 2>&1 | tail -40

echo ""
echo "=== Done. Open http://192.168.0.113/ in your desktop browser. ==="
echo "=== /kiosk route:   http://192.168.0.113/kiosk ==="
echo "=== tar1090 passthrough:  http://192.168.0.113/tar1090/ ==="
