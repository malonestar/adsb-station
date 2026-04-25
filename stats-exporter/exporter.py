"""Prometheus exporter for readsb stats served by Ultrafeeder.

Polls http://ultrafeeder/data/stats.json + /data/aircraft.json at STATS_INTERVAL
and exposes gauges at :8080/metrics. Runs in its own container on adsb_net.

Why this exists: Ultrafeeder's `:latest` image doesn't ship with telegraf, so the
documented `:9273` Prometheus exporter is non-functional. This replaces it.
"""

import math
import os
import time
import threading
from urllib.request import urlopen
import json
import logging

from prometheus_client import start_http_server, Gauge

UPSTREAM = os.environ.get("ULTRAFEEDER_URL", "http://ultrafeeder")
INTERVAL = int(os.environ.get("STATS_INTERVAL", "15"))
LISTEN_PORT = int(os.environ.get("LISTEN_PORT", "8080"))

# Earth radius in nautical miles (for great-circle distance).
_R_NM = 3440.065

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stats-exporter")


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in nautical miles."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return _R_NM * c


def compute_polar_bins(outline_points, station_lat: float, station_lon: float):
    """Collapse the 360-bearing outline into 36 ten-degree maximum-range bins.

    ``outline_points`` must have exactly 360 entries; entry ``i`` is
    ``[lat, lon, alt_ft]`` for integer compass bearing ``i`` (0 = north,
    clockwise). Returns a list of 36 floats (nautical miles), bin ``b``
    covering bearings ``[b*10, b*10+10)``.
    """
    if len(outline_points) != 360:
        raise ValueError(f"expected 360 outline points, got {len(outline_points)}")

    bins = [0.0] * 36
    for i, pt in enumerate(outline_points):
        lat, lon = pt[0], pt[1]
        d = haversine_nm(station_lat, station_lon, lat, lon)
        b = i // 10
        if d > bins[b]:
            bins[b] = d
    return bins


def update_polar(station_lat: float, station_lon: float) -> None:
    """Refresh the ``adsb_polar_range_nm`` gauge from Ultrafeeder's outline.json.

    Fetches ``/data/outline.json``, extracts ``actualRange.last24h.points``,
    bins into 36 ten-degree bearing slices, and publishes one labelled
    series per bin. Swallows all exceptions (logs a warning) so a bad
    upstream response never takes the collector down.
    """
    try:
        outline = fetch_json("/data/outline.json")
        points = (
            outline.get("actualRange", {})
            .get("last24h", {})
            .get("points")
        )
        if not points:
            log.warning("update_polar: outline.json missing actualRange.last24h.points")
            return
        bins = compute_polar_bins(points, station_lat, station_lon)
        for b, value in enumerate(bins):
            polar_range_nm.labels(bearing=str(b * 10)).set(value)
    except Exception as e:
        log.warning("update_polar failed: %s", e)


# --- Metric definitions ---
# Aircraft
aircraft_observed = Gauge("adsb_aircraft_observed", "Aircraft currently tracked")
aircraft_with_position = Gauge("adsb_aircraft_with_position", "Aircraft with a known lat/lon")
aircraft_without_position = Gauge("adsb_aircraft_without_position", "Aircraft without position")

# Signal quality (from stats.json.last1min.local)
signal_dbfs = Gauge("adsb_signal_dbfs", "Mean signal strength (dBFS) over last minute")
noise_dbfs = Gauge("adsb_noise_dbfs", "Noise floor (dBFS) over last minute")
peak_signal_dbfs = Gauge("adsb_peak_signal_dbfs", "Peak signal strength (dBFS) over last minute")
strong_signals = Gauge("adsb_strong_signals_per_min", "Strong signals count over last minute")

# Receiver
gain_db = Gauge("adsb_gain_db", "Current RTL-SDR gain (dB)")
max_distance_m = Gauge("adsb_max_distance_meters", "Max aircraft distance observed last minute (meters)")

# Messages
messages_per_min = Gauge("adsb_messages_per_min", "Valid messages accepted in last minute")
modes_per_min = Gauge("adsb_mode_s_per_min", "Mode-S frames detected in last minute")
bad_per_min = Gauge("adsb_bad_frames_per_min", "Bad frames in last minute")

# Polar coverage — per-10-degree compass bearing bin, last 24h
polar_range_nm = Gauge(
    "adsb_polar_range_nm",
    "Max observed range per 10-degree compass bearing bin (nautical miles), last 24h",
    labelnames=["bearing"],
)

# Position decoder health
cpr_airborne = Gauge("adsb_cpr_airborne_per_min", "Airborne CPR position decodes last minute")
cpr_global_ok = Gauge("adsb_cpr_global_ok_per_min", "Successful global CPR decodes last minute")
cpr_local_ok = Gauge("adsb_cpr_local_ok_per_min", "Successful local CPR decodes last minute")

# Scrape health
scrape_ok = Gauge("adsb_exporter_scrape_success", "1 if last upstream poll succeeded, 0 otherwise")
scrape_duration = Gauge("adsb_exporter_scrape_duration_seconds", "Duration of the last upstream poll")


def fetch_json(path: str) -> dict:
    url = f"{UPSTREAM.rstrip('/')}{path}"
    with urlopen(url, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


# Station coords are lazy-loaded from /data/receiver.json on first use,
# with env var fallback. `None` means "not yet resolved"; a tuple means
# "resolved, cache this across scrape cycles".
_station_coords: "tuple[float, float] | None" = None
# Tracks whether we've already logged the "unresolved" warning, so the
# warning fires once instead of every 15s tick while we keep trying.
_station_warned_unresolved = False


def _ensure_station_coords():
    """Return (lat, lon) for the station, or ``None`` if unresolved.

    Resolution order (cached after first success):
      1. /data/receiver.json -> top-level ``lat`` / ``lon``
      2. env vars ``STATION_LAT`` / ``STATION_LON``
    """
    global _station_coords, _station_warned_unresolved

    if _station_coords is not None:
        return _station_coords

    try:
        recv = fetch_json("/data/receiver.json")
        lat = recv.get("lat")
        lon = recv.get("lon")
        if lat is not None and lon is not None:
            _station_coords = (float(lat), float(lon))
            log.info("station coords resolved from receiver.json: lat=%.4f lon=%.4f", *_station_coords)
            return _station_coords
    except Exception as e:
        log.warning("receiver.json fetch failed while resolving station coords: %s", e)

    env_lat = os.environ.get("STATION_LAT")
    env_lon = os.environ.get("STATION_LON")
    if env_lat and env_lon:
        try:
            _station_coords = (float(env_lat), float(env_lon))
            log.info("station coords resolved from env: lat=%.4f lon=%.4f", *_station_coords)
            return _station_coords
        except ValueError as e:
            log.warning("STATION_LAT/STATION_LON env vars are not numeric: %s", e)

    if not _station_warned_unresolved:
        log.warning(
            "station coords unresolved — receiver.json had no lat/lon and "
            "STATION_LAT/STATION_LON env vars are not set; skipping polar update"
        )
        _station_warned_unresolved = True
    return None


def collect_once() -> None:
    started = time.monotonic()
    try:
        stats = fetch_json("/data/stats.json")
        aircraft = fetch_json("/data/aircraft.json")
    except Exception as e:
        scrape_ok.set(0)
        scrape_duration.set(time.monotonic() - started)
        log.warning("upstream poll failed: %s", e)
        return

    # Aircraft counts
    ac_list = aircraft.get("aircraft", [])
    total = len(ac_list)
    with_pos = sum(1 for a in ac_list if a.get("lat") is not None and a.get("lon") is not None)
    aircraft_observed.set(total)
    aircraft_with_position.set(with_pos)
    aircraft_without_position.set(total - with_pos)

    # Stats — prefer last1min if present
    window = stats.get("last1min") or {}
    local = window.get("local") or {}
    signal_dbfs.set(local.get("signal", 0))
    noise_dbfs.set(local.get("noise", 0))
    peak_signal_dbfs.set(local.get("peak_signal", 0))
    strong_signals.set(local.get("strong_signals", 0))
    modes_per_min.set(local.get("modes", 0))
    bad_per_min.set(local.get("bad", 0))

    cpr = window.get("cpr") or {}
    cpr_airborne.set(cpr.get("airborne", 0))
    cpr_global_ok.set(cpr.get("global_ok", 0))
    cpr_local_ok.set(cpr.get("local_ok", 0))

    messages_per_min.set(window.get("messages", 0))
    max_distance_m.set(window.get("max_distance", 0))

    # Top-level stats (current snapshot, not windowed)
    gain_db.set(stats.get("gain_db", 0))

    scrape_ok.set(1)
    scrape_duration.set(time.monotonic() - started)

    coords = _ensure_station_coords()
    if coords is not None:
        update_polar(coords[0], coords[1])


def main() -> None:
    log.info("starting stats-exporter on :%d, polling %s every %ds", LISTEN_PORT, UPSTREAM, INTERVAL)
    start_http_server(LISTEN_PORT)
    while True:
        collect_once()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
