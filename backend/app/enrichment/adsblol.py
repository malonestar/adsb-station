"""adsb.lol REST — free, open route lookup.

Docs: https://api.adsb.lol/docs
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.enrichment.cache import cache
from app.enrichment.circuit import CircuitBreaker
from app.logging import get_logger

log = get_logger(__name__)
_breaker = CircuitBreaker(name="adsblol")
_SOURCE = "adsblol_route"

# Global-context cache: a single bucket of nearby-aircraft results, refreshed
# at most once per `_GLOBAL_TTL_S` seconds. Keyed on (lat, lon, dist) rounded
# to mute trivial coord drift; in practice we only ever ask about the station's
# coords so this is effectively a singleton cache.
import time as _time
_GLOBAL_TTL_S = 5.0
_global_cache: dict[tuple[float, float, int], tuple[float, list[dict[str, Any]]]] = {}


async def lookup_nearby(lat: float, lon: float, dist_nm: int) -> list[dict[str, Any]]:
    """Pull all aircraft within `dist_nm` of (lat, lon) from adsb.lol.

    Returns a slim representation per aircraft (hex, callsign, lat, lon,
    alt_baro, gs, track, type, category) — drops the bulky Mode-S / RSSI
    fields we don't need for a faded overlay. Empty list on any error.
    Cached server-side for a few seconds so multiple frontends don't each
    hit adsb.lol independently.
    """
    key = (round(lat, 3), round(lon, 3), int(dist_nm))
    now = _time.monotonic()
    hit = _global_cache.get(key)
    if hit is not None and now - hit[0] < _GLOBAL_TTL_S:
        return hit[1]

    if _breaker.is_open:
        return hit[1] if hit is not None else []

    # adsb.lol /v2 endpoint shape: /lat/{lat}/lon/{lon}/dist/{nm}
    base = settings.adsblol_base.rstrip("/")
    url = f"{base}/lat/{lat}/lon/{lon}/dist/{int(dist_nm)}"
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_s) as c:
            r = await c.get(url, headers={"User-Agent": "adsb-tracker/0.1"})
        r.raise_for_status()
        data = r.json()
        _breaker.record_success()
    except Exception as e:  # noqa: BLE001
        log.warning("adsblol_nearby_failed", error=str(e))
        _breaker.record_failure()
        return hit[1] if hit is not None else []

    raw = data.get("ac") or []
    out: list[dict[str, Any]] = []
    for a in raw:
        # adsb.lol uses string altitudes ("ground", or stringified ints).
        alt_baro = a.get("alt_baro")
        if isinstance(alt_baro, str):
            alt_baro = None if alt_baro == "ground" else _try_int(alt_baro)
        out.append(
            {
                "hex": (a.get("hex") or "").lower(),
                "flight": (a.get("flight") or "").strip() or None,
                "lat": a.get("lat"),
                "lon": a.get("lon"),
                "alt_baro": alt_baro,
                "gs": a.get("gs"),
                "track": a.get("track"),
                "type_code": a.get("t") or None,
                "category": a.get("category") or None,
            }
        )
    _global_cache[key] = (now, out)
    return out


def _try_int(s: str) -> int | None:
    try:
        return int(s)
    except (TypeError, ValueError):
        return None


async def lookup_route(callsign: str) -> dict[str, Any] | None:
    """Look up origin/destination airports for a callsign (IATA/ICAO flight)."""
    callsign = callsign.strip().upper()
    if not callsign:
        return None

    cached = await cache.get(callsign, _SOURCE)
    if cached is not None:
        return cached if not cached.get("not_found") else None

    if _breaker.is_open:
        return None

    url = f"{settings.adsblol_base}/api/0/route/{callsign}"
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_s) as c:
            r = await c.get(url, headers={"User-Agent": "adsb-tracker/0.1"})
        if r.status_code == 404:
            _breaker.record_success()
            await cache.set(callsign, _SOURCE, {"not_found": True}, ttl_days=7, http_status=404)
            return None
        r.raise_for_status()
        data = r.json()
        normalized = _normalize(data)
        if normalized is None:
            await cache.set(callsign, _SOURCE, {"not_found": True}, ttl_days=7)
            return None
        _breaker.record_success()
        await cache.set(callsign, _SOURCE, normalized, ttl_days=30, http_status=r.status_code)
        return normalized
    except (httpx.HTTPError, ValueError) as e:
        log.warning("adsblol_route_failed", callsign=callsign, error=str(e))
        _breaker.record_failure()
        return None


def _normalize(raw: dict[str, Any]) -> dict[str, Any] | None:
    airports = raw.get("_airports") or []
    if len(airports) < 2:
        return None
    origin = airports[0]
    dest = airports[-1]
    return {
        "origin_iata": origin.get("iata"),
        "origin_icao": origin.get("icao"),
        "origin_name": origin.get("name"),
        "dest_iata": dest.get("iata"),
        "dest_icao": dest.get("icao"),
        "dest_name": dest.get("name"),
        "airline_iata": (raw.get("airline_iata") if isinstance(raw.get("airline_iata"), str) else None),
        "airline_name": (raw.get("airline_name") if isinstance(raw.get("airline_name"), str) else None),
    }
