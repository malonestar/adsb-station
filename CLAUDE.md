# ADS-B Aircraft Tracking Station + Custom Dashboard

## Current State

🛩️ LIVE · 📡 8/8 feeders claimed · 📻 1090 + 978 dual-band (UAT pip + filter toggle) · 📊 Grafana observability · 🔔 Telegram + Discord alerts · 🤖 interactive bot · 🗺️ heatmap + history overlays · 📱 PWA + mobile drawer · 🔒 Tailscale remote access · 🗺️ flight route enrichment · ✈️ aircraft-type icons · 🛬 airport boards · 🌐 global-context overlay · 📋 watchlist with notify-toggle + UAT chip

The station is fully operational. Plans 2, 3D-1, and 3B are complete. **Source on GitHub: https://github.com/malonestar/adsb-station** — Pi pushes directly via deploy key. Build narrative and dated milestones live in [`docs/PROJECT_HISTORY.md`](docs/PROJECT_HISTORY.md). Pre-execution brainstorm preserved in [`docs/PROJECT_VISION.md`](docs/PROJECT_VISION.md).

Running at `http://192.168.0.113/` (LAN) or `http://adsb-pi/` (Tailscale MagicDNS).

## Hardware

- Pi 5 (16GB) + 1TB Samsung T7 USB SSD
- **Two RTL-SDR dongles, serial-pinned** (USB enumeration order is non-deterministic across reboots):
  - **FlightAware Pro Stick Plus (serial `1090`)** — 1090 MHz ADS-B leg. **Built-in LNA + 1090 SAW filter.** Swapped in 2026-07-03, replacing the Nooelec NESDR SMArt v5 (which USB-flapped with `error -71` and failed; Nooelec now a spare).
  - FlightAware Pro Stick (serial `978`) — 978 MHz UAT leg
- **RF chain:** outdoor dual-band vertical antenna on garage conduit → 10ft coax → 2-way SMA splitter →
  - **Leg A (1090):** Pro Stick Plus (built-in 1090 filter + LNA) → USB cable → Pi. **No external SAW filter** — the Pro Stick Plus's filter sits *after* its amp; adding an external one before it would add ~2 dB NF in our clean RF environment. External 1090 SAW filter kept as a spare. (Swap raised aircraft count ~30 → ~110.)
  - **Leg B (978):** FA dual-band 1090+978 bandpass filter → FA Pro Stick → USB cable → Pi
- Station: 39.692°N, 105.020°W (3-decimal rounded for privacy)
- OS: Debian Trixie 13.3, Python 3.13.5; OS on SD card, everything else on SSD at `/mnt/ssd`
- **T7 SSD negotiates USB 2.0 (480M) speed** even in a blue USB3 port — it's the cable (or T7 bridge), not the port. Left on USB2 deliberately: fine for the write load AND avoids USB3's ~2.4 GHz RFI near the SDRs/WiFi. Only chase USB3 (with the T7's original Gen2 cable) if disk throughput is ever needed.

## Host & networking (non-Docker)

- **WiFi (2026-07-03):** Pi is on **WiFi** (`wlan0`, internal Broadcom), `eth0` down. NetworkManager conn **`wifi-2g`** → SSID `TheSquirmingCoil` (2.4 GHz), pinned to `wlan0`, **power-save disabled** (`802-11-wireless.powersave 2`), holds `.113` via DHCP reservation on the internal radio's MAC. 5 GHz `preconfigured` kept as a pinned-to-wlan0 fallback. Moved off marginal 5 GHz + killed power-save to stop intermittent drop-offs. A Panda PAU09 USB WiFi dongle was tested and **removed** — measured identical to the internal radio on 2.4 GHz (−56 dBm), no benefit where it sat.
- **SDR auto-recovery watchdog (2026-07-03):** host systemd timer **`adsb-sdr-watchdog.timer`** (every 60 s) runs `/mnt/ssd/adsb/scripts/sdr-watchdog.sh`. If the 1090 dongle wedges (USB `error -71` flap → readsb `sdrOpen() failed`, `aircraft.json` goes stale), it USB-resets the dongle's port (`authorized` toggle, port resolved by serial `1090`) + restarts ultrafeeder, with 240 s cooldown, gives up + Telegram-alerts after 4 tries. Install: `scripts/install-sdr-watchdog.sh`. Logs: `journalctl -t adsb-sdr-watchdog`. State: `/var/lib/adsb-sdr-watchdog/`. Manual recovery (same steps): stop ultrafeeder → `echo 0|sudo tee /sys/bus/usb/devices/<port>/authorized; sleep 2; echo 1|sudo tee …` → start ultrafeeder.

## Services running

`docker compose` at `/mnt/ssd/adsb/` — 12 containers on custom `adsb_net` network:

- `ultrafeeder` — readsb + tar1090 + graphs1090 + mlat-client. Pinned to dongle serial `1090` via `READSB_RTLSDR_DEVICE`. Ingests UAT raw stream from `dump978` via `READSB_NET_CONNECTOR=dump978,30978,uat_in` so tar1090 + outbound aggregators see merged 1090+978. **Also feeds ADS-B Exchange, adsb.lol, adsb.fi, airplanes.live** via `ULTRAFEEDER_CONFIG` env var (4 community aggregators inline, no per-aggregator containers). Needs service-level `UUID` and `MLAT_USER` env vars or mlat-client refuses to launch.
- `dump978` — 978 MHz UAT decoder (sdr-enthusiasts/docker-dump978). Pinned to dongle serial `978` via `DUMP978_RTLSDR_DEVICE`. Exposes raw faup978 stream on `:30978` consumed by ultrafeeder + piaware. UAT-Out aircraft (US GA below 18k ft) appear in tar1090 with `uat_version: 2` field.
- `adsb-backend` — FastAPI + SQLite + WebSocket + enrichment (hexdb, Planespotters, adsb.lol, adsbdb, FA AeroAPI)
- `adsb-frontend` — nginx reverse-proxying React SPA + `/api` + `/ws` + `/tar1090` + `/graphs1090` + `/grafana`
- `piaware` — FlightAware feeder. Relay-mode from ultrafeeder:30005 for 1090 + UAT relay-mode from dump978:30978 (`UAT_RECEIVER_TYPE=relay`, `UAT_RECEIVER_HOST=dump978`). Both bands credit the same FA site 273304, account `malonestar`.
- `rbfeeder` — AirNav Radar (fka RadarBox). Serial `EXTRPI722821`.
- `opensky-feeder` — Serial `-1407998386` (negative is legit int32), sensor 917863. **Must persist `OPENSKY_SERIAL` to `.env` or it regenerates every restart.**
- `fr24feed` — Flightradar24. Station `KAPA185`. `MLAT=no` per FR24's policy (the only aggregator that requires MLAT off when sharing with other networks).
- `adsb-stats-exporter` — custom Python Prometheus exporter (reads ultrafeeder's `/data/*.json`, publishes `adsb_*` metrics on `:8080`). Exists because Ultrafeeder `:latest` ships without telegraf, so `:9273` is non-functional.
- `prometheus` — TSDB, 365d/50GB retention. Scrapes stats-exporter + node-exporter + self.
- `grafana` — dashboards at `/grafana/` subpath; admin + anonymous Viewer.
- `node-exporter` — Pi system metrics (CPU temp, memory, disk, net).

Feeder services live in a separate override file `/mnt/ssd/adsb/docker-compose.feeders.yml`. Bring them up with:

```bash
docker compose -f docker-compose.yml -f docker-compose.feeders.yml up -d
```

## URLs

| What | Where |
|---|---|
| Custom dashboard | http://192.168.0.113/ |
| Touchscreen kiosk view | http://192.168.0.113/kiosk |
| tar1090 fallback | http://192.168.0.113/tar1090/ |
| graphs1090 | http://192.168.0.113/graphs1090/ |
| Grafana | http://192.168.0.113/grafana/ — admin pw in `/mnt/ssd/adsb/.env` `GRAFANA_ADMIN_PW`; anonymous viewing works without login |

## Grafana dashboards

- **ADS-B Live Receiver Health** (custom, 13 panels) — daily-driver desktop dashboard. Embedded in Stats page's RECEIVER HEALTH tab above 768px.
- **ADS-B Live Receiver Health (Mobile)** — UID `adsb-receiver-health-mobile`, single-column variant for <768px viewports. Embedded in same Stats tab below 768px.
- **ADS-B Antenna Comparison** — antenna-install before/after story with `hardware-change` annotations.
- **Node Exporter Full** — community 1860, deep Pi system visibility.

## Alert system (Phase 3B)

- **5 rule kinds:** `military`, `emergency` (squawks 7500/7600/7700), `interesting`, `watchlist` (27+ entries), `high_altitude` (>45k ft).
- **Military / interesting classification:** readsb `dbFlags` PLUS operator-string regex match in `app/enrichment/classifier.py` (covers USAF/Army/Navy/Marine/Coast Guard, Air National Guard, DoD, CBP, allied air forces, NASA→interesting, FAA/NOAA/DOE/DARPA/USFS→interesting). In-memory `known_military_hexes` / `known_interesting_hexes` sets are loaded from catalog at startup, grown by enrichment coordinator, consulted by parser when building `AircraftState`. Backfill: `await classifier.backfill_from_catalog()`.
- **Channels firing:** Telegram (bot `@ADSB_ms_bot`, chat_id 7553531136) + Discord webhook. Email/SMTP intentionally disabled — uncomment six `ADSB_SMTP_*` vars in `/mnt/ssd/adsb/.env` to re-enable.
- **Cooldowns:** per-(hex, kind) 6h, plus `cooldown_overrides` table for persistent `/mute`. Emergency bypasses both. **Re-notify on +10k climb** also bypasses (publishes `alert.renotify` event for high_altitude alerts; `HIGH_ALT_CLIMB_RENOTIFY_FT = 10_000`).
- **High-altitude payload tracks peak alt:** `_maybe_update_peak_alt` writes `peak_alt_ft` into the alert row's payload as the aircraft climbs. Notification labels trigger-time alt as "Crossed at X ft" and shows "Peak: Y ft" when peak differs. Climb-renotify shows "Climb: X → Y ft".
- **Manual test:** `POST /api/alerts/test {"channel":"telegram|discord|email|all"}` fires a synthetic alert through configured channels. Setup guide: `pi-setup/alerts/README.md`.

### Interactive Telegram bot

`@ADSB_ms_bot` runs long-polling (`getUpdates?timeout=30`) — no webhook, no public URL needed. Module: `app/telegram_bot/`. Single-user gate via `ADSB_TELEGRAM_CHAT_ID`.

- **Commands:** `/status` `/nearest` `/last [N]` `/watch <hex> [label]` `/unwatch <hex>` `/help`
- **Reply-to-alert vocabulary:** reply with `watch` / `mute` / `info` / anything-else (help nudge). Lookup via `telegram_message_map` table.

## Watchlist tab

Dedicated `/watchlist` route (between CATALOG and STATS in TopBar). **Responsive layout** — dense sortable+searchable table on desktop (lg+), card grid below lg. Header summary `N entries · N notifying · N passive · N live`. Live count also surfaces as a badge in the TopBar nav (`WATCHLIST 2 LIVE` in amber when matches are in range).

`+ ADD` modal supports all 4 kinds: **HEX / REG / TYPE / OPERATOR** with kind-aware placeholder + validation. Each entry has a `notify` boolean (Alembic 0006) — `kind=hex` defaults notify=True (deliberate per-aircraft picks); `reg/type/operator` default to **passive** (still flag matched aircraft on the watchlist tab + WATCHLIST badge in alerts feed, but no Telegram/Discord push) to avoid flood when matching e.g. `type=B738`. Per-entry **🔔 NOTIFY ↔ 🔕 PASSIVE** toggle in the row clicks to flip in place via `PATCH /api/watchlist/{id}`. Cold-add for unseen hexes triggers `EnrichmentCoordinator.enrich_cold(hex)` which fires hexdb + planespotters lookups one time and creates a stub `AircraftCatalog` row with epoch timestamps + `seen_count=0`. Photo click opens fullscreen lightbox (`src/components/chrome/PhotoLightbox.tsx`, shared with the radar detail panel).

Operator-kind entries are passive-only in V1 — operator data lives in the catalog, not in `AircraftState`, so the alert evaluator can't match without a cross-reference. Modal explains this; the notify checkbox is disabled for operator kind.

WATCH button on the radar detail panel toggles via `useToggleWatch` (visual state: ghost → primary "WATCHING ✓"). TRACK button engages `followSelection` so the map auto-pans to the aircraft on every position update.

## Alerts feed

`/alerts` is a card-based "recent catches" feed (rebuilt from a table). Each card: photo thumbnail · kind badge with emoji · flight + reg + type + operator · alert details (alt / dist / squawk / climb history) · age. ACTIVE pill on uncleared alerts (left border lights up phos green). IN RANGE pill when the aircraft is currently in the live registry. "climb update" marker on re-notified high-altitude alerts. Filter chips show per-kind counts; click any card → dashboard with that aircraft selected, map pans to it. Backend `/api/alerts` and `/api/alerts/live` LEFT JOIN `aircraft_catalog` so photos/operator/reg come through inline.

## Aircraft icons (radar)

Categorical SVG silhouettes drive the marker shape: heavy (4-engine widebody), narrowbody (2 engines), bizjet (compact swept + T-tail), GA prop (straight wings + prop disc), helicopter (rotor disc + tail boom, compact — no wings extending sideways), glider, drone. Selection by ICAO `category` first (A1–A7, B1/B2/B6) with type-code prefix fallback (Cessna/Piper/Mooney → gaprop, Citation/Gulfstream/Lear/Falcon → bizjet, EC/AS/UH/AH/CH/R-series → rotor, etc.) covering ~150 type codes. Body silhouette is **never overridden by is_military** — military and interesting are non-rotating overlay badges (amber dot for military, violet dot for interesting) on the parent so a USAF C-17 reads as a heavy with a military pip, not a generic "military" shape. RC-135 reads as a narrowbody with the same amber pip.

**Three orthogonal overlay pips:**
- **Amber dot, top-right (`::after`)** — `is_military` (readsb dbFlags OR operator regex)
- **Violet dot, top-right (`::after`)** — `is_interesting` (mutually exclusive with mil at the markup level — only one of mil/int renders)
- **Cyan dot, top-left (`::before`)** — `uat_version` truthy (UAT-decoded aircraft). Stacks independently with the mil/int badge so a USAF UAT-equipped helicopter shows both amber and cyan simultaneously.

## Band differentiation (UAT 978 vs ADS-B 1090)

**Radar map 📻 button** (last in the right-control stack, after 🌐) cycles a tri-state filter — `all` (📻 icon, default) → `uat-only` (cyan "978" label) → `no-uat` (cyan "1090" label) → `all`. Filter respects `selectedHex` so the detail panel never desyncs from the map. Implementation: `useHistory.uatFilter` + `cycleUatFilter` in `src/store/history.ts`; `AircraftMarkers.tsx` filters its render list.

**Detail panel `SRC` line** (under operator) shows current band: `ADS-B 1090 MHz` or `UAT 978 MHz` (cyan). When `live.uat_version` is null but the catalog flag `ever_seen_uat` is true, an `(also seen on UAT)` hint trails the line.

**Catalog `UAT 978` chip** (between INTERESTING and HAS PHOTO) filters `/api/catalog?category=uat`. Backend filter is `AircraftCatalog.ever_seen_uat.is_(True)`. The flag is **sticky once set** — `_upsert_catalog` (enrichment time) flips it via Python attribute, and `_update_catalog_stats` (every tick, raw SQL CASE) flips it for pre-UAT-era catalog rows that get a UAT sighting after the fact.

`AircraftState.uat_version: int | None` mirrors readsb's sticky field exactly — readsb keeps it set after a UAT sighting even if the aircraft is currently 1090-only. So "currently on UAT" cannot be inferred from a single tick; we treat the flag as "ever seen on UAT this session" on the live side, and `ever_seen_uat` as "ever seen on UAT in this catalog" on the persistent side.

## Airport boards (`/airports`)

Tabs for **DEN / APA / BKF / FTG**. Side-by-side APPROACHING / DEPARTING columns on desktop, stacked on mobile, with proper column headers (Call · Type · Alt AGL · V/S · Dist · Route · Speed). Each row: callsign · type · alt AGL (above field elevation) · v/s · distance to that airport · origin → destination from route enrichment. Click any row → radar with that aircraft tracked.

**Bucketing logic** (backend `/api/airports/traffic`):
1. **Route data wins** — if `route.destination` matches a board airport AND aircraft is descending, → APPROACHING that airport. Same logic for `route.origin` + climbing → DEPARTING.
2. **Closest-airport fallback** for aircraft without matching route data (GA traffic without flight plans, transient overflights, stale callsign data).
3. **Commercial-hub override** — if the closest-airport fallback would assign a known commercial-airline callsign (UAL/AAL/DAL/SWA/FFT/SKW/etc.) to a GA-only field (KAPA/KBKF/KFTG), redirect to the commercial hub (KDEN). Stale callsign data is the rule, not the exception — adsbdb keys per-callsign-not-per-flight-instance and airline flight numbers get reused for different OD pairs throughout the day.

`route_cache` is **eagerly populated** by the enrichment coordinator now — every observed callsign gets resolved within ~5–10 seconds of first sighting (cached 6h hit / 1h miss). Previously route_cache only filled when a user clicked the detail panel, which meant the airport boards' route-match path almost never fired.

Rendering: TanStack Query `placeholderData: keepPreviousData` keeps the table populated during refetch; `MovementRow` is `React.memo` with field-by-field equality (distance rounded to 0.1 nm) so unchanged rows don't repaint on each 5s tick.

## Global-context toggle

🌐 button in the radar's map controls. When ON: backend `/api/aircraft/global` proxies adsb.lol's `/v2/lat/lon/dist` endpoint (5s server-side TTL cache, dedup against own live registry) within 200 nm of the station. Frontend renders the result as a faded HTML overlay (60% opacity, 16px markers, no labels) BELOW the primary marker layer so own catches always win z-stacking. Off by default; opt-in. Doesn't touch alerts, catalog, watchlist, or DB — purely visual.

## Tech stack

Python 3.13 + FastAPI + SQLAlchemy async + Alembic + structlog. React 19 + TypeScript + Vite + deck.gl v9 + Tailwind v4 + Zustand v5 + TanStack Query + Framer Motion. nginx 1.27 alpine. Prometheus + Grafana 10.

## Where to pick up next session

Full session-to-session state lives in memory files at `C:\Users\khmal\.claude\projects\C--Users-khmal-Projects-Vessel-Tracking\memory\`. Start with `MEMORY.md` index; `project_adsb_status.md` has canonical live state. Claude has direct SSH access to the Pi as `adsb-pi` (see `user_pi_ssh_access.md`).

## Next Steps (priority order)

### 1. Optional / deferred

- **Operator-kind watchlist alerting** — V1 limitation: operator data lives in catalog, not `AircraftState`, so alert eval can't match without a cross-reference. Modal currently disables the notify checkbox for operator kind. Workaround would be a hex-set populated from catalog (similar to `known_military_hexes`) that grows as operator-matching catalog rows enrich.
- **Mobile UX pass on the alerts feed** — verify the new card layout reads well on phone; tweak as needed.
- **Phosphor-themed panels in React `/stats`** — was Plan 3D stage 2. Probably skip; the Grafana iframe embed serves the role.

## Active Docs

- Plan 3D (observability) spec: `docs/superpowers/specs/2026-04-20-grafana-observability-design.md`
- Plan 3D plan: `docs/superpowers/plans/2026-04-20-adsb-plan-3d1-grafana-observability.md` (executed)
- Plan 3D bundle: `pi-setup/grafana-prometheus/`
- Plan 3B (alerts) spec: `docs/superpowers/specs/2026-04-21-alert-notifications-design.md`
- Plan 3B plan: `docs/superpowers/plans/2026-04-21-adsb-plan-3b-alert-notifications.md` (executed)
- Plan 3B bundle: `pi-setup/alerts/` (source of truth for notifications). User-facing setup at `pi-setup/alerts/README.md`.
- Receiver Health dashboard spec: `docs/superpowers/specs/2026-04-23-grafana-receiver-health-dashboard-design.md`
- Receiver Health dashboard plan: `docs/superpowers/plans/2026-04-23-grafana-receiver-health-dashboard.md` (executed)

## Known Non-Issues (don't "fix")

- **Pi CPU 80°C during heavy Docker builds** (soft thermal limit) — normal. Steady-state ADS-B load alone runs 50–60°C with active cooling.
- **`0B / 0B` in `docker stats` memory column** — cgroups v2 reporting quirk on Pi's kernel.
- **Backend probe of `http://ultrafeeder/data/stats.json` was 404** — probe removed; msgs/sec is computed from aircraft snapshots directly.
- **Pi-hole users:** must whitelist `basemaps.cartocdn.com` so basemap tiles load.
- **Ultrafeeder `:9273` does NOT serve Prometheus** — `:latest` image ships without telegraf. Use the `adsb-stats-exporter` container instead. Don't be tempted to "fix" by pointing Prometheus at `:9273`.
- **Grafana text panels need `GF_PANELS_DISABLE_SANITIZE_HTML=true`** to render HTML mode (otherwise raw `<a>`/`<style>` tags show as literal text). Set in `docker-compose.observability.yml` grafana env — don't try to "fix" plain-text rendering by escaping; check the env var first.
- **Grafana subpath proxy_pass:** nginx `proxy_pass http://grafana:3000;` must NOT have trailing slash. With `SERVE_FROM_SUB_PATH=true`, the trailing slash strips the prefix and causes an infinite 301 loop.
- **Grafana iframe needs `GF_SECURITY_ALLOW_EMBEDDING=true`** — already enabled to let the Stats page's RECEIVER HEALTH tab embed the dashboard. Don't remove — Grafana defaults to `X-Frame-Options: DENY`.
- **Gain is autogain-managed; expect a LOW value now (NOT 49.6)** — since the 2026-07-03 Pro Stick Plus swap the 1090 leg has a built-in LNA, so the correct RTL gain is far below the old Nooelec's 49.6 dB (49.6 over-drove the amp: peak −1.1 dBFS clipping, ~6% strong signals). Autogain was reset (`docker exec ultrafeeder autogain1090 reset`) and re-converges from the amp — let it settle over ~1 h. Don't "fix" a non-49.6 gain; that's expected now. Verify via `docker exec ultrafeeder cat /var/globe_history/autogain/gain`; watch convergence with `docker logs ultrafeeder --since 24h | grep -iE "autogain|gain"`. Saturation sanity: `strong_signals`/`messages` in `/run/readsb/stats.json` should sit ≲5–6%. (Pre-swap note, for history: the old Nooelec was signal-starved and wanted more gain than the SDR could give.)
- **Heatmap cold fetch is now ~1-4s** (down from 15-20s) — the `position_cells_hourly` rollup table aggregates positions hourly at 0.02° resolution. Heatmap endpoint reads the rollup for fully-elapsed hours and merges with a live aggregation over the trailing partial hour. Backfill: `await app.stats.aggregates.backfill_position_cells_all()`. Hourly cron at :05 UTC keeps it current. Don't try to bypass for "perf reasons" — the rollup IS the perf path.
- **Dongles pinned by serial, not USB index** — 1090 leg (Pro Stick Plus) is `1090`, 978 leg (Pro Stick) is `978` (written via `rtl_eeprom -d N -s NEW`). Compose uses `READSB_RTLSDR_DEVICE=1090` and `DUMP978_RTLSDR_DEVICE=978`. USB enumeration order genuinely flips between reboots. Don't "simplify" by switching to numeric indexes. Verify serials non-disruptively via sysfs: `for d in /sys/bus/usb/devices/*/; do [ "$(cat $d/idVendor 2>/dev/null)" = 0bda ] && echo "$(basename $d) $(cat $d/serial)"; done`; or `docker run --rm --entrypoint rtl_eeprom --device /dev/bus/usb ghcr.io/sdr-enthusiasts/docker-adsb-ultrafeeder:latest -d 0` (after stopping ultrafeeder + dump978). **Writing a new eeprom serial needs a real power cycle/reboot to take effect — a soft USB re-enumerate (authorized toggle) does NOT refresh the reported serial.**
- **dump978 startup logs `usb_claim_interface error -6` and `[R82XX] PLL not locked!`** during init — both clear within a few seconds and the decoder works fine afterwards. Don't try to "fix" them; they're benign first-attempt warnings during USB device claim.
- **SPA `index.html` is served `Cache-Control: no-store, must-revalidate`** in `pi-setup/adsb/frontend/nginx.conf` — required so iOS/Android home-screen PWA icons see new builds without manual cache clears. `/assets/*` keep `public, immutable, max-age=31536000` because Vite hashes the filenames. Don't "tighten" the asset cache or "loosen" the index cache without understanding which deploy pattern fails.
