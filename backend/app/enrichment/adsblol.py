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
