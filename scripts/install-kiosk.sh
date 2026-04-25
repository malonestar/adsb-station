#!/usr/bin/env bash
# One-shot installer for the kiosk systemd user service.
# Safe to re-run. Does NOT enable kiosk mode — only wires up the auto-launcher.
# Toggle kiosk on/off by editing ENABLE_KIOSK_DISPLAY in /mnt/ssd/adsb/.env.

set -eu

echo "=== 1. Install chromium + helpers ==="
sudo apt install -y chromium unclutter xdotool x11-xserver-utils

echo ""
echo "=== 2. Make launcher executable ==="
chmod +x /mnt/ssd/adsb/scripts/adsb-kiosk.sh

echo ""
echo "=== 3. Install systemd user unit ==="
mkdir -p "$HOME/.config/systemd/user"
cp /mnt/ssd/adsb/scripts/adsb-kiosk.service "$HOME/.config/systemd/user/adsb-kiosk.service"
systemctl --user daemon-reload
systemctl --user enable adsb-kiosk.service

echo ""
echo "=== 4. Enable systemd user lingering (so service runs without login session) ==="
sudo loginctl enable-linger "$USER"

echo ""
echo "=== Done. To activate kiosk mode: ==="
echo "  1. Attach the 7\" touchscreen"
echo "  2. Edit /mnt/ssd/adsb/.env and set ENABLE_KIOSK_DISPLAY=true"
echo "  3. Reboot (sudo reboot) — Chromium will auto-launch fullscreen to http://localhost/kiosk"
echo ""
echo "To disable: set ENABLE_KIOSK_DISPLAY=false and reboot."
