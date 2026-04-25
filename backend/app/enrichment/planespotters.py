"""Planespotters.net photo lookup.

Docs: https://www.planespotters.net/photo/api
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.enrichment.cache import cache
from app.enrichment.circuit import CircuitBreaker
from app.logging import get_logger

log = get_logger(__name__)
_breaker = CircuitBreaker(name="planespotters")
_SOURCE = "planespotters"


async def lookup(hex_code: str) -> dict[str, Any] | None:
    hex_code = hex_code.lower()
    cached = await cache.get(hex_code, _SOURCE)
    if cached is not None:
        return cached if not cached.get("not_found") else None

    if _breaker.is_open:
        return None

    url = f"{settings.planespotters_base}/photos/hex/{hex_code}"
    try:
        async with httpx.AsyncClient(timeout=settings.http_timeout_s) as c:
            r = await c.get(url, headers={"User-Agent": "adsb-tracker/0.1 (malonestar)"})
        r.raise_for_status()
        data = r.json()
        photos = data.get("photos") or []
        if not photos:
            _breaker.record_success()
            await cache.set(hex_code, _SOURCE, {"not_found": True}, ttl_days=7)
            return None
        photo = photos[0]
        normalized = _normalize(photo)
        _breaker.record_success()
        await cache.set(hex_code, _SOURCE, normalized, http_status=r.status_code)
        return normalized
    except (httpx.HTTPError, ValueError) as e:
        log.warning("planespotters_lookup_failed", hex=hex_code, error=str(e))
        _breaker.record_failure()
        return None


def _normalize(photo: dict[str, Any]) -> dict[str, Any]:
    thumb = photo.get("thumbnail_large") or photo.get("thumbnail") or {}
    return {
        "photo_id": photo.get("id"),
        "photo_url": (photo.get("thumbnail_large") or {}).get("src") if isinstance(photo.get("thumbnail_large"), dict) else None,
        "photo_thumb_url": thumb.get("src") if isinstance(thumb, dict) else None,
        "photo_photographer": photo.get("photographer"),
        "photo_link": photo.get("link"),
    }
