"""OpenSky REST — global context aircraft beyond our antenna range.

Docs: https://openskynetwork.github.io/opensky-api/rest.html
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.enrichment.circuit import CircuitBreaker
from app.logging import get_logger

log = get_logger(__name__)
_breaker = CircuitBreaker(name="opensky")


async def states_in_bbox(
    min_lat: float, min_lon: float, max_lat: float, max_lon: float
) -> list[dict[str, Any]]:
    if _breaker.is_open:
        return []
    url = f"{settings.opensky_base}/states/all"
    params = {
        "lamin": min_lat,
        "lomin": min_lon,
        "lamax": max_lat,
        "lomax": max_lon,
    }
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_s) as c:
            r = await c.get(url, params=params, headers={"User-Agent": "adsb-tracker/0.1"})
        r.raise_for_status()
        data = r.json()
        states = data.get("states") or []
        _breaker.record_success()
        return [_normalize_state(row) for row in states]
    except (httpx.HTTPError, ValueError) as e:
        log.warning("opensky_states_failed", error=str(e))
        _breaker.record_failure()
        return []


def _normalize_state(row: list[Any]) -> dict[str, Any]:
    """OpenSky states_all returns a compact array — map to named fields."""
    # Index 0: icao24, 1: callsign, 2: origin_country, 5: longitude, 6: latitude,
    # 7: baro_altitude, 9: velocity, 10: true_track, 11: vertical_rate,
    # 14: geo_altitude
    return {
        "hex": row[0].strip().lower() if row[0] else None,
        "callsign": (row[1] or "").strip() or None,
        "country": row[2],
        "lon": row[5],
        "lat": row[6],
        "alt_baro_m": row[7],
        "gs_mps": row[9],
        "track": row[10],
        "vs_mps": row[11],
        "alt_geom_m": row[13] if len(row) > 13 else None,
    }
