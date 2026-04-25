"""hexdb.io client — ICAO hex → registration/type/operator.

Docs: https://hexdb.io/
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.enrichment.cache import cache
from app.enrichment.circuit import CircuitBreaker
from app.logging import get_logger

log = get_logger(__name__)
_breaker = CircuitBreaker(name="hexdb")
_SOURCE = "hexdb"


async def lookup(hex_code: str) -> dict[str, Any] | None:
    """Return normalized aircraft info dict or None."""
    hex_code = hex_code.lower()
    cached = await cache.get(hex_code, _SOURCE)
    if cached is not None:
        return cached

    if _breaker.is_open:
        return None

    url = f"{settings.hexdb_base}/aircraft/{hex_code}"
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_s) as c:
            r = await c.get(url, headers={"User-Agent": "adsb-tracker/0.1 (malonestar)"})
        if r.status_code == 404:
            _breaker.record_success()
            # Negative-cache 404s briefly so we don't hammer on every hex seen
            await cache.set(hex_code, _SOURCE, {"not_found": True}, ttl_days=7, http_status=404)
            return None
        r.raise_for_status()
        data = r.json()
        normalized = _normalize(data)
        _breaker.record_success()
        await cache.set(hex_code, _SOURCE, normalized, http_status=r.status_code)
        return normalized
    except (httpx.HTTPError, ValueError) as e:
        log.warning("hexdb_lookup_failed", hex=hex_code, error=str(e))
        _breaker.record_failure()
        return None


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "registration": raw.get("Registration"),
        "type_code": raw.get("ICAOTypeCode"),
        "type_name": raw.get("Type"),
        "operator": raw.get("RegisteredOwners"),
        "manufacturer": raw.get("Manufacturer"),
    }
