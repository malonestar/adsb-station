#!/usr/bin/env bash
# Install/enable the ADS-B SDR watchdog (script lives in this repo scripts/ dir).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

chmod +x "$HERE/sdr-watchdog.sh"
sudo install -m 0644 "$HERE/adsb-sdr-watchdog.service" /etc/systemd/system/adsb-sdr-watchdog.service
sudo install -m 0644 "$HERE/adsb-sdr-watchdog.timer"   /etc/systemd/system/adsb-sdr-watchdog.timer
sudo systemctl daemon-reload
sudo systemctl enable --now adsb-sdr-watchdog.timer

echo "Installed. Timer status:"
systemctl status adsb-sdr-watchdog.timer --no-pager | head -6
echo
echo "Next runs:"; systemctl list-timers adsb-sdr-watchdog.timer --no-pager
echo "Logs: journalctl -t adsb-sdr-watchdog -f   (or: journalctl -u adsb-sdr-watchdog.service)"
