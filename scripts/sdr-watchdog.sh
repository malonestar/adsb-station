#!/usr/bin/env bash
# adsb-sdr-watchdog — auto-recover a wedged/flapping RTL-SDR on the 1090 leg.
#
# Failure it heals: the 1090 dongle drops into a USB connect/disconnect flap
# (kernel: "device descriptor read/all, error -71"), its RTL2832 controller
# wedges, and readsb can no longer open it ("sdrOpen() failed", crash-loops).
# Result: no 1090 data -> ultrafeeder 0 aircraft -> piaware unhealthy/red dot.
#
# Recovery: stop ultrafeeder, force a clean USB re-enumeration of the dongle's
# port (authorized toggle), restart ultrafeeder. Cooldown + backoff prevent
# reset storms; gives up + alerts if resets stop helping (likely dead hardware).
#
# Installed as a oneshot service fired every 60s by adsb-sdr-watchdog.timer.
set -uo pipefail

# ---- config ---------------------------------------------------------------
SDR_SERIAL="1090"          # serial of the 1090-leg dongle (readsb --device=1090)
FALLBACK_PORT="1-2"        # USB port to reset if the serial can't be resolved
CONTAINER="ultrafeeder"
STALE_SECS=120             # aircraft.json older than this => decoder not writing
COOLDOWN_SECS=240          # min gap between recovery attempts
MAX_CONSECUTIVE=4          # after N back-to-back recoveries, stop + alert
STATE_DIR="/var/lib/adsb-sdr-watchdog"
STATE_FILE="$STATE_DIR/state"      # "<last_epoch> <consecutive>"
GAVEUP_MARK="$STATE_DIR/gaveup"
ENV_FILE="/mnt/ssd/adsb/.env"
# ---------------------------------------------------------------------------

log() { echo "$*"; logger -t adsb-sdr-watchdog "$*" 2>/dev/null || true; }

notify() {
  # Best-effort Telegram ping using creds already in the stack .env
  local msg="$1" tok chat
  [ -f "$ENV_FILE" ] || return 0
  tok=$(grep -E '^ADSB_TELEGRAM_BOT_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2-)
  chat=$(grep -E '^ADSB_TELEGRAM_CHAT_ID=' "$ENV_FILE" | head -1 | cut -d= -f2-)
  tok=${tok%\"}; tok=${tok#\"}; tok=$(printf '%s' "$tok" | tr -d '[:space:]')
  chat=${chat%\"}; chat=${chat#\"}; chat=$(printf '%s' "$chat" | tr -d '[:space:]')
  [ -n "$tok" ] && [ -n "$chat" ] || return 0
  curl -s -m 10 "https://api.telegram.org/bot${tok}/sendMessage" \
    --data-urlencode "chat_id=${chat}" \
    --data-urlencode "text=${msg}" >/dev/null 2>&1 || true
}

mkdir -p "$STATE_DIR"
now=$(date +%s)
last_epoch=0; consecutive=0
[ -f "$STATE_FILE" ] && read -r last_epoch consecutive < "$STATE_FILE" || true
: "${last_epoch:=0}"; : "${consecutive:=0}"

# 0. Only act if the container is meant to be running (don't fight manual stops).
running=$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || echo missing)
if [ "$running" != "true" ]; then
  log "container $CONTAINER not running (state=$running); skipping"
  exit 0
fi

# 1. Health check: readsb rewrites aircraft.json ~every second when decoding
#    (even with zero aircraft), so staleness == decoder not producing.
age=$(docker exec "$CONTAINER" sh -c \
  'if [ -f /run/readsb/aircraft.json ]; then echo $(( $(date +%s) - $(stat -c %Y /run/readsb/aircraft.json) )); else echo 99999; fi' \
  2>/dev/null || echo 99999)

if [ "$age" -lt "$STALE_SECS" ]; then
  if [ "$consecutive" != "0" ] || [ -f "$GAVEUP_MARK" ]; then
    log "decoder healthy again (aircraft.json age ${age}s); clearing backoff"
    [ -f "$GAVEUP_MARK" ] && notify "✅ ADS-B watchdog: 1090 decoder recovered; auto-recovery re-armed."
    rm -f "$GAVEUP_MARK"
  fi
  echo "$last_epoch 0" > "$STATE_FILE"
  exit 0
fi

# 2. Decoder is down. Confirm it's the SDR-open failure (the flap/wedge case),
#    not some unrelated stall — only USB resets are appropriate for the wedge.
if ! docker logs "$CONTAINER" --since 90s 2>&1 | \
     grep -qE "sdrOpen\(\) failed|no device matching|unable to read device details|usb_claim_interface error"; then
  log "aircraft.json stale (${age}s) but no SDR-open error in last 90s; not a USB wedge — leaving for manual review"
  exit 0
fi

# 3. Backoff / give-up guard.
if [ "$consecutive" -ge "$MAX_CONSECUTIVE" ]; then
  if [ ! -f "$GAVEUP_MARK" ]; then
    log "GAVE UP: ${consecutive} consecutive USB resets did not recover the 1090 dongle — likely dead dongle/cable/port. Halting auto-recovery."
    notify "🛑 ADS-B watchdog gave up after ${consecutive} USB resets on the 1090 dongle. Resets aren't helping — likely hardware (cable/connector/dongle). Manual check needed."
    touch "$GAVEUP_MARK"
  fi
  exit 1
fi

# 4. Cooldown guard (let a prior recovery finish spinning up).
if [ $(( now - last_epoch )) -lt "$COOLDOWN_SECS" ]; then
  log "in cooldown ($(( now - last_epoch ))s < ${COOLDOWN_SECS}s); waiting for prior recovery to settle"
  exit 0
fi

# 5. Resolve the USB port hosting serial=SDR_SERIAL; fall back to FALLBACK_PORT.
port=""
for d in /sys/bus/usb/devices/*; do
  if [ -f "$d/serial" ] && [ "$(cat "$d/serial" 2>/dev/null)" = "$SDR_SERIAL" ]; then
    port=$(basename "$d"); break
  fi
done
[ -z "$port" ] && port="$FALLBACK_PORT"

attempt=$((consecutive + 1))
log "1090 decoder down (aircraft.json ${age}s stale, SDR-open error present). Recovering: USB reset port ${port} + restart ${CONTAINER} (attempt #${attempt})"

# 6. Recovery: release device -> USB port re-enumerate -> restart.
docker stop "$CONTAINER" >/dev/null 2>&1
if [ -w "/sys/bus/usb/devices/$port/authorized" ]; then
  echo 0 > "/sys/bus/usb/devices/$port/authorized" 2>/dev/null
  sleep 2
  echo 1 > "/sys/bus/usb/devices/$port/authorized" 2>/dev/null
  sleep 3
else
  log "WARN: /sys/bus/usb/devices/$port/authorized not writable; restarting container only"
fi
docker start "$CONTAINER" >/dev/null 2>&1

echo "$now $attempt" > "$STATE_FILE"
log "recovery issued (attempt #${attempt}); verifying on next tick"
notify "🔧 ADS-B watchdog: 1090 dongle was wedged (USB error). Reset port ${port} + restarted ultrafeeder (attempt #${attempt})."
exit 0
