# adsb-station

A Raspberry Pi-based ADS-B aircraft tracking station with a custom web
dashboard, alerting, observability, and feeds to all major aggregators. The
Pi runs the full stack as Docker containers; one terminal command brings up
decoder + dashboard + alerts + feeders + Grafana.

The codebase is the deployed state of the station at 39.692°N, 105.020°W
(Aurora, CO). It's published as-is for reference and re-use — fork it,
edit `.env`, point it at your antenna, and the dashboard, watchlist, and
airport boards work the same.

## Hardware

- **Raspberry Pi 5, 16 GB RAM** — runs everything (decoder, backend,
  frontend, Prometheus, Grafana, all feeders) as Docker containers. CPU
  steady-state ~50–60 °C with active cooling. Pi 4 (4 GB+) would also
  work; you'd want to drop the global-context overlay or the heatmap
  rollup to keep it under thermal throttle.
- **Nooelec NESDR SMArt v5** USB SDR dongle — same R820T2 / RTL2832U
  chipset as the RTL-SDR Blog V3, functionally equivalent. ~$25.
- **1 TB Samsung T7 USB SSD** — mounted at `/mnt/ssd`. Holds Docker
  daemon data, project source, the SQLite DB, the Prometheus TSDB, and
  the Grafana database. The SD card holds only the OS so we don't burn
  through write cycles. ~$80.
- **Antenna**: outdoor 1090 MHz vertical on a garage conduit mount,
  10 ft of LMR-240 coax, **SAW filter at the dongle**. Filter placement
  at the dongle (rather than at the antenna) is correct per noise-chain
  theory. Max range with this setup is around 180 nm; signal floor sits
  around −41 dBFS, well below readsb's autogain "too noisy" threshold.
- **OS**: Debian Trixie 13.3, Python 3.13. Tailscale installed for
  remote access (no public ports opened).

A 978 MHz UAT integration is planned (FA Pro Stick Plus + dual-band
filter + 2-way RF splitter on order). Will pick up GA traffic from
nearby airports the 1090-only setup misses.

## Docker stack

Eleven containers in three logical groups, all on a custom `adsb_net`
network. Compose files live at the repo root:

- `docker-compose.yml` — core (decoder, backend, frontend)
- `docker-compose.feeders.yml` — Phase-2 aggregator clients
- `docker-compose.observability.yml` — Prometheus + Grafana + exporters

### Decoder / feed layer

| Container | Image | Role |
|---|---|---|
| `ultrafeeder` | `ghcr.io/sdr-enthusiasts/docker-adsb-ultrafeeder:latest` | readsb decoder, tar1090 map, graphs1090 stats, mlat-client. Also runs inline feeds to ADS-B Exchange, adsb.lol, adsb.fi, and airplanes.live via `ULTRAFEEDER_CONFIG` — no separate containers needed for those four. Needs service-level `UUID` and `MLAT_USER` env vars (per-entry `uuid=` is not enough; mlat-client refuses to start without them). |
| `piaware` | `ghcr.io/sdr-enthusiasts/docker-piaware:latest` | FlightAware feeder, relay-mode from `ultrafeeder:30005`. |
| `rbfeeder` | `ghcr.io/sdr-enthusiasts/docker-radarbox:latest` | AirNav Radar (formerly RadarBox). |
| `fr24feed` | `ghcr.io/sdr-enthusiasts/docker-flightradar24:latest` | Flightradar24. `MLAT=no` per FR24's policy — they're the one aggregator that requires MLAT off when sharing with other networks. |
| `opensky-feeder` | `ghcr.io/sdr-enthusiasts/docker-opensky-network:latest` | OpenSky Network. The first-run serial must be persisted to `.env` as `FEEDER_OPENSKY_SERIAL` or the container regenerates a new one on every restart. |

Aggregator credentials come from `.env`. See `.env.example` for every
key the stack consumes.

### Application layer

| Container | Source | Role |
|---|---|---|
| `adsb-backend` | `backend/` | FastAPI + SQLAlchemy async + Alembic + structlog. Polls `ultrafeeder:80/data/aircraft.json` every second, normalizes into `AircraftState`, runs alert evaluation and enrichment (hexdb / Planespotters / adsbdb / FA AeroAPI cascade), and exposes `/api/*` + `/ws`. SQLite DB at `/mnt/ssd/data/db/adsb.db`. APScheduler runs daily and hourly maintenance jobs (catalog rollup, position retention prune, heatmap rollup). |
| `adsb-frontend` | `frontend/` | React 19 + TypeScript + Vite + deck.gl v9 + Tailwind v4 + Zustand + TanStack Query, served by nginx 1.27-alpine. nginx also reverse-proxies `/api`, `/ws`, `/tar1090`, `/graphs1090`, and `/grafana` so the dashboard, fallback map, and observability stack all live behind a single port-80 endpoint. |

### Observability layer

| Container | Image | Role |
|---|---|---|
| `prometheus` | `prom/prometheus:v3.0.1` | Time-series DB, 365 d / 50 GB retention. Scrapes `adsb-stats-exporter`, `node-exporter`, and itself. |
| `grafana` | `grafana/grafana:11.4.0` | Dashboards at `/grafana/`. Anonymous Viewer access enabled; admin password from `.env`. Provisioned dashboards live in `grafana-prometheus/grafana/provisioning/dashboards/json/`. |
| `node-exporter` | `prom/node-exporter:v1.8.2` | Pi system metrics (CPU temp, memory, disk, network). |
| `adsb-stats-exporter` | `stats-exporter/` | Custom Python Prometheus exporter. Reads ultrafeeder's `/data/*.json` files and publishes `adsb_*` metrics on port 8080. Exists because the `ultrafeeder:latest` image ships without telegraf, so the documented `:9273` endpoint is non-functional. Don't try to "fix" by pointing Prometheus at `:9273` — use this exporter. |

### Bringing it up

```bash
cd /mnt/ssd/adsb
cp .env.example .env
# fill in feeder credentials, Telegram/Discord tokens, Grafana password
docker compose -f docker-compose.yml \
  -f docker-compose.feeders.yml \
  -f docker-compose.observability.yml \
  up -d
docker compose run --rm adsb-backend alembic upgrade head
```

Or set `COMPOSE_FILE=docker-compose.yml:docker-compose.feeders.yml:docker-compose.observability.yml`
in `.env` and just `docker compose up -d`.

## Repository layout

```
.
├── backend/                      Python FastAPI service
│   ├── app/
│   │   ├── api/                  REST + WebSocket routes
│   │   ├── alerts/               Rules, watchlist, cooldown overrides
│   │   ├── enrichment/           hexdb + planespotters + adsbdb + AeroAPI
│   │   ├── notifications/        Telegram / Discord / email adapters
│   │   ├── readsb/               Aircraft.json parser + poller
│   │   ├── stats/                Live stats + daily/hourly rollups
│   │   ├── telegram_bot/         Long-poll command handler (@ADSB_ms_bot)
│   │   ├── history/              Catalog + heatmap + replay queries
│   │   ├── db/                   SQLAlchemy models + Alembic migrations
│   │   └── events/               In-process event bus
│   ├── tests/                    pytest, ~144 tests
│   └── Dockerfile
├── frontend/                     React 19 SPA
│   ├── src/
│   │   ├── components/           map (deck.gl), chrome (Panel/Button/etc), panels, layout
│   │   ├── routes/               Dashboard, Catalog, Watchlist, Alerts, Stats, Feeds, Airports, Settings, Kiosk, Replay
│   │   ├── store/                Zustand stores (aircraft, alerts, history, selection, settings, stats, feeds)
│   │   ├── lib/                  api client, format helpers, watchlist hook, airport metadata
│   │   ├── styles/               Tailwind globals, theme tokens
│   │   └── types/                Shared TypeScript shapes
│   ├── public/icons/             Aircraft-type silhouettes (heavy, narrow, bizjet, gaprop, rotor, glider, drone)
│   ├── nginx.conf                Reverse-proxy config
│   └── Dockerfile
├── stats-exporter/               Python Prometheus exporter for ultrafeeder
├── grafana/                      Grafana provisioning (dashboards JSON, datasources YAML)
├── prometheus/                   prometheus.yml
├── scripts/                      One-shot deploy / kiosk helpers
├── docker-compose.yml            Core stack
├── docker-compose.feeders.yml    Phase-2 aggregator override
├── docker-compose.observability.yml
└── .env.example                  Every env var the stack reads
```

## Configuration

Everything that varies per-station lives in `.env`. The committed
`.env.example` documents all keys with comments. Quick reference:

- **Station location** — `FEEDER_LAT`, `FEEDER_LON`, `FEEDER_ALT_M`,
  `FEEDER_TZ`, `FEEDER_NAME`. Round coords to 3–4 decimals if publishing.
- **SDR** — `READSB_GAIN=autogain` is fine; `READSB_RTLSDR_DEVICE=0` for
  the first SDR.
- **Feeder credentials** — `FEEDER_PIAWARE_FEEDER_ID`,
  `FEEDER_FR24_SHARING_KEY`, `FEEDER_RB_SHARING_KEY`,
  `FEEDER_ADSBX_UUID`, `FEEDER_OPENSKY_USERNAME`,
  `FEEDER_OPENSKY_SERIAL`. Get each from the respective network's
  signup flow.
- **Notifications** — `ADSB_TELEGRAM_BOT_TOKEN` (from @BotFather),
  `ADSB_TELEGRAM_CHAT_ID`, `ADSB_DISCORD_WEBHOOK_URL`. Email/SMTP
  vars are optional and currently commented out.
- **Optional paid APIs** — `ADSB_FLIGHTAWARE_AEROAPI_KEY` is used
  only as Tier-3 fallback for flight route lookups when adsbdb and
  hexdb both miss. Realistic worst-case spend ~$0.50/month. Leave
  empty to skip.
- **Observability** — `GRAFANA_ADMIN_PW` (any string).

## Features built on top

- **Live radar** with deck.gl map, custom HTML marker overlay,
  category-driven aircraft silhouettes, military / interesting overlay
  badges, range rings, optional sweep + scanline aesthetic.
- **Catalog** — every aircraft ever observed by the station, sortable
  + searchable + filterable by category. CSV export.
- **Watchlist** — hex / registration / type / operator entries with
  per-entry notify toggle (passive vs active), cold-add via
  `+ ADD` modal, photo lightbox, click-through to track on radar.
- **Alerts feed** — recent catches as a card stream (military, emergency,
  interesting, watchlist, high-altitude). Photos + route attribution +
  click-through.
- **Airport boards** — DEN/APA/BKF/FTG approaching / departing tables
  with route-data-aware bucketing and a commercial-hub override that
  prevents misclassifying airline traffic to GA-only fields.
- **Heatmap overlay** with 1H / 24H / 7D / ALL windows. 30 days of
  positions back the rollup table; 1.4–4 s cold fetch on full-window.
- **Global-context toggle** — overlays adsb.lol traffic within 200 nm
  as faded markers so you can see ambient context beyond your antenna's
  reach.
- **Stats page** with Grafana iframe embed + LIVE STATS view (responsive
  variant of receiver-health dashboard).
- **Feeds page** — per-aggregator status table.
- **Telegram bot** (`@ADSB_ms_bot`, replace with your own) with reply-
  to-alert vocabulary (`watch`, `mute`, `info`) plus `/status`,
  `/nearest`, `/last`, `/watch`, `/unwatch`, `/help`.
- **PWA + Tailscale** — installable on iOS/Android home screen, share-
  node flow lets friends view from their own tailnet without exposing
  any public ports.

## Notes / gotchas

- The `ultrafeeder:latest` image does not ship with telegraf. The
  `:9273` Prometheus endpoint is non-functional. Use the bundled
  `adsb-stats-exporter` instead.
- nginx `proxy_pass http://grafana:3000;` must NOT have a trailing
  slash. With `GF_SERVER_SERVE_FROM_SUB_PATH=true`, the trailing slash
  strips the prefix and produces an infinite 301 loop.
- Grafana text panels need `GF_PANELS_DISABLE_SANITIZE_HTML=true` to
  render HTML mode properly.
- Grafana iframe embedding (used by the Stats page) needs
  `GF_SECURITY_ALLOW_EMBEDDING=true`.
- Pi-hole users need to whitelist `basemaps.cartocdn.com` so the
  basemap tiles load.
- A heavy Docker build can push the Pi to ~80 °C briefly. Steady-state
  is well below that with active cooling.

## Development

The Pi is the source of truth for deployed code. The repo is git-
initialized at `/mnt/ssd/adsb`; commits go directly to GitHub via a
deploy key. Suggested workflow:

```bash
ssh adsb-pi
cd /mnt/ssd/adsb
# edit
git add -A && git commit -m "..."
git push
# then rebuild the affected service
docker compose build adsb-backend && docker compose up -d adsb-backend
```

Tests run inside the backend container (the production image excludes
test deps and tests/, so install + mount):

```bash
docker exec adsb-backend pip install --quiet pytest pytest-asyncio aiosqlite
docker cp tests adsb-backend:/app/tests
docker exec -w /app -e PYTHONPATH=/app adsb-backend \
  python -m pytest tests/ --asyncio-mode=auto
```

## License

No license declared yet. Treat as all-rights-reserved until otherwise
noted; reach out if you want to use any of the more reusable bits
(operator classifier, alert pipeline, heatmap rollup pattern, etc.).
