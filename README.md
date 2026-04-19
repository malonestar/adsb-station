# ADS-B Tracker - Aurora, CO

Custom ADS-B aircraft tracking station + dashboard.

- Hardware: Raspberry Pi 5 16GB + Nooelec NESDR SMArt v5 + 1TB Samsung T7 SSD
- Station: 39.7 N, -104.8 W, ~5400ft MSL
- Storage: OS on SD card; Docker data-root, project code, SQLite DB on SSD at /mnt/ssd
- Design spec: docs/superpowers/specs/2026-04-19-adsb-tracker-design.md

## Quick start

    cd /mnt/ssd/adsb
    docker compose up -d
    # tar1090 map: http://<pi-ip>/tar1090
    # graphs1090:  http://<pi-ip>/graphs1090
    # Dashboard:   http://<pi-ip>/              (Plan 2)
