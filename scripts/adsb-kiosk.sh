#!/usr/bin/env bash
# Kiosk launcher for the 7" touchscreen.
# Run by the systemd user service adsb-kiosk.service.
# Does nothing unless ENABLE_KIOSK_DISPLAY=true in /mnt/ssd/adsb/.env.

set -eu

ENV_FILE="${ADSB_ENV_FILE:-/mnt/ssd/adsb/.env}"

if [ ! -r "$ENV_FILE" ]; then
  echo "[kiosk] no env file at $ENV_FILE — exiting"
  exit 0
fi

# Load .env (safe — file is project-owned)
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

if [ "${ENABLE_KIOSK_DISPLAY:-false}" != "true" ]; then
  echo "[kiosk] ENABLE_KIOSK_DISPLAY != true — exiting"
  exit 0
fi

KIOSK_URL="${KIOSK_URL:-http://localhost/kiosk}"

# Wait for a display to be available (Wayland or X11) — up to 120s.
# default.target fires before the graphical session on some Pi OS setups.
echo "[kiosk] waiting for display server"
for i in $(seq 1 120); do
  if [ -n "${WAYLAND_DISPLAY:-}" ] && [ -S "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/${WAYLAND_DISPLAY}" ]; then
    echo "[kiosk] Wayland display ready after ${i}s"
    break
  fi
  if [ -n "${DISPLAY:-}" ] && xdpyinfo >/dev/null 2>&1; then
    echo "[kiosk] X11 display ready after ${i}s"
    break
  fi
  sleep 1
done

# Wait for the frontend to respond (up to 90s) before launching the browser
echo "[kiosk] waiting for frontend at http://localhost/healthz"
for i in $(seq 1 90); do
  if curl -fsS http://localhost/healthz >/dev/null 2>&1; then
    echo "[kiosk] frontend ready after ${i}s"
    break
  fi
  sleep 1
done

# Hide the mouse cursor when idle
if command -v unclutter >/dev/null 2>&1; then
  unclutter -idle 1 -root &
fi

# Prevent screen blanking (Xorg path — safe no-op on Wayland)
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true
xset s noblank 2>/dev/null || true

# Launch Chromium in kiosk mode
#  --password-store=basic — suppresses the gnome-keyring unlock prompt
#  --no-default-browser-check — skips the "make Chromium default?" prompt
#  --disable-session-crashed-bubble — hides "restore pages?" after unclean shutdown
exec chromium \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-translate \
  --disable-pinch \
  --overscroll-history-navigation=disabled \
  --check-for-update-interval=31536000 \
  --disable-features=TranslateUI,ChromeWhatsNewUI \
  --password-store=basic \
  --no-default-browser-check \
  --disable-session-crashed-bubble \
  --disable-restore-session-state \
  --no-first-run \
  --start-maximized \
  --app="${KIOSK_URL}"
