"""Flight origin/destination enrichment.

On-demand fetch (user clicks aircraft), 3-tier fallback:
    1. adsbdb.com        — free, rich, no auth, ~100 req/min
    2. hexdb.io          — free, sparse (just ICAO codes)
    3. FlightAware AeroAPI — metered (~$0.005/call), requires key

Results are cached in the `route_cache` table keyed by callsign:
    - hits  (source != "not_found")   — cached `route_cache_hit_ttl_hours` (6h)
    - misses (source == "not_found")  — cached `route_cache_miss_ttl_hours` (1h)

Concurrent clicks are protected by a per-process asyncio semaphore so we don't
saturate the upstreams.
"""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select

from app.config import settings
from app.db.models import RouteCache
from app.db.session import session_scope
from app.logging import get_logger

log = get_logger(__name__)


@dataclass
class Airport:
    icao: str
    iata: str | None
    name: str
    city: str | None


@dataclass
class RouteInfo:
    callsign: str
    origin: Airport | None
    destination: Airport | None
    airline: str | None
    source: str  # adsbdb | hexdb | aeroapi | not_found

    def to_dict(self) -> dict[str, Any]:
        return {
            "callsign": self.callsign,
            "origin": asdict(self.origin) if self.origin else None,
            "destination": asdict(self.destination) if self.destination else None,
            "airline": self.airline,
            "source": self.source,
        }


def _normalize_callsign(callsign: str | None) -> str | None:
    if not callsign:
        return None
    s = callsign.strip().upper()
    if not s or len(s) > 16:
        return None
    return s


def _now() -> datetime:
    return datetime.now(UTC)


def _row_to_route(row: RouteCache) -> RouteInfo:
    origin = None
    if row.origin_icao:
        origin = Airport(
            icao=row.origin_icao,
            iata=row.origin_iata,
            name=row.origin_name or row.origin_icao,
            city=row.origin_city,
        )
    destination = None
    if row.destination_icao:
        destination = Airport(
            icao=row.destination_icao,
            iata=row.destination_iata,
            name=row.destination_name or row.destination_icao,
            city=row.destination_city,
        )
    return RouteInfo(
        callsign=row.callsign,
        origin=origin,
        destination=destination,
        airline=row.airline_name,
        source=row.source,
    )


class RouteService:
    def __init__(self) -> None:
        # Bound concurrent outbound calls per source so a burst of clicks
        # doesn't accidentally DoS an aggregator.
        self._sem_adsbdb = asyncio.Semaphore(2)
        self._sem_hexdb = asyncio.Semaphore(2)
        self._sem_aeroapi = asyncio.Semaphore(2)

    async def get_route(self, callsign: str | None) -> RouteInfo | None:
        norm = _normalize_callsign(callsign)
        if norm is None:
            return None

        # 1. Cache lookup
        cached = await self._cache_get(norm)
        if cached is not None:
            return cached

        # 2. Try each tier. Return the first hit; otherwise cache a miss.
        result = await self._fetch_adsbdb(norm)
        if result is None:
            result = await self._fetch_hexdb(norm)
        if result is None and settings.flightaware_aeroapi_key:
            result = await self._fetch_aeroapi(norm)

        if result is None:
            result = RouteInfo(
                callsign=norm,
                origin=None,
                destination=None,
                airline=None,
                source="not_found",
            )

        await self._cache_put(result)
        return result

    # ─── Cache helpers ──────────────────────────────────────────────────

    async def _cache_get(self, callsign: str) -> RouteInfo | None:
        async with session_scope() as s:
            row = (
                await s.execute(
                    select(RouteCache).where(RouteCache.callsign == callsign)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            fetched = row.fetched_at
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=UTC)
            if row.source == "not_found":
                max_age = timedelta(hours=settings.route_cache_miss_ttl_hours)
            else:
                max_age = timedelta(hours=settings.route_cache_hit_ttl_hours)
            if _now() - fetched > max_age:
                return None
            return _row_to_route(row)

    async def _cache_put(self, route: RouteInfo) -> None:
        async with session_scope() as s:
            existing = (
                await s.execute(
                    select(RouteCache).where(RouteCache.callsign == route.callsign)
                )
            ).scalar_one_or_none()
            data = {
                "callsign": route.callsign,
                "origin_icao": route.origin.icao if route.origin else None,
                "origin_iata": route.origin.iata if route.origin else None,
                "origin_name": route.origin.name if route.origin else None,
                "origin_city": route.origin.city if route.origin else None,
                "destination_icao": route.destination.icao if route.destination else None,
                "destination_iata": route.destination.iata if route.destination else None,
                "destination_name": route.destination.name if route.destination else None,
                "destination_city": route.destination.city if route.destination else None,
                "airline_name": route.airline,
                "source": route.source,
                "fetched_at": _now(),
            }
            if existing is None:
                s.add(RouteCache(**data))
            else:
                for k, v in data.items():
                    setattr(existing, k, v)

    # ─── Tier 1: adsbdb.com ─────────────────────────────────────────────

    async def _fetch_adsbdb(self, callsign: str) -> RouteInfo | None:
        url = f"{settings.adsbdb_base}/callsign/{callsign}"
        async with self._sem_adsbdb:
            try:
                async with httpx.AsyncClient(timeout=settings.http_timeout_s) as c:
                    r = await c.get(
                        url,
                        headers={"User-Agent": "adsb-tracker/0.1 (malonestar)"},
                    )
                if r.status_code == 404:
                    return None
                if r.status_code == 429:
                    log.warning("adsbdb_rate_limited", callsign=callsign)
                    return None
                if r.status_code >= 400:
                    log.warning(
                        "adsbdb_http_error",
                        callsign=callsign,
                        status=r.status_code,
                    )
                    return None
                data = r.json()
            except (httpx.HTTPError, ValueError) as e:
                log.warning("adsbdb_fetch_failed", callsign=callsign, error=str(e))
                return None

        route = (data or {}).get("response", {}).get("flightroute")
        if not route:
            return None

        origin_raw = route.get("origin") or {}
        dest_raw = route.get("destination") or {}
        airline_raw = route.get("airline") or {}

        def _airport(raw: dict[str, Any]) -> Airport | None:
            icao = raw.get("icao_code")
            if not icao:
                return None
            return Airport(
                icao=icao,
                iata=raw.get("iata_code"),
                name=raw.get("name") or icao,
                city=raw.get("municipality"),
            )

        origin = _airport(origin_raw)
        destination = _airport(dest_raw)
        if origin is None and destination is None:
            return None

        return RouteInfo(
            callsign=callsign,
            origin=origin,
            destination=destination,
            airline=airline_raw.get("name"),
            source="adsbdb",
        )

    # ─── Tier 2: hexdb.io ───────────────────────────────────────────────

    async def _fetch_hexdb(self, callsign: str) -> RouteInfo | None:
        url = f"{settings.hexdb_base}/route/icao/{callsign}"
        async with self._sem_hexdb:
            try:
                async with httpx.AsyncClient(timeout=settings.http_timeout_s) as c:
                    r = await c.get(
                        url,
                        headers={"User-Agent": "adsb-tracker/0.1 (malonestar)"},
                    )
                if r.status_code == 404:
                    return None
                if r.status_code >= 400:
                    log.warning(
                        "hexdb_route_http_error",
                        callsign=callsign,
                        status=r.status_code,
                    )
                    return None
                body = r.text.strip()
                if not body:
                    return None
                data = r.json()
            except (httpx.HTTPError, ValueError) as e:
                log.warning("hexdb_route_fetch_failed", callsign=callsign, error=str(e))
                return None

        route_str = (data or {}).get("route")
        if not route_str:
            return None
        # "KPHL-KDEN" or multi-leg "KLAX-KJFK-EGLL" — take first+last
        parts = [p.strip() for p in route_str.split("-") if p.strip()]
        if len(parts) < 2:
            return None
        origin_icao = parts[0]
        dest_icao = parts[-1]
        # hexdb gives only ICAO. Use them as both icao+name.
        return RouteInfo(
            callsign=callsign,
            origin=Airport(icao=origin_icao, iata=None, name=origin_icao, city=None),
            destination=Airport(icao=dest_icao, iata=None, name=dest_icao, city=None),
            airline=None,
            source="hexdb",
        )

    # ─── Tier 3: FlightAware AeroAPI ─────────────────────────────────────

    async def _fetch_aeroapi(self, callsign: str) -> RouteInfo | None:
        key = settings.flightaware_aeroapi_key
        if not key:
            return None
        url = f"{settings.flightaware_aeroapi_base}/flights/{callsign}"
        # Cost-tracking log line — grep to count daily calls.
        log.info("aeroapi_call", endpoint="flights", ident=callsign)
        async with self._sem_aeroapi:
            try:
                async with httpx.AsyncClient(timeout=settings.http_timeout_s) as c:
                    r = await c.get(
                        url,
                        headers={
                            "x-apikey": key,
                            "Accept": "application/json",
                            "User-Agent": "adsb-tracker/0.1 (malonestar)",
                        },
                    )
                if r.status_code in (402, 403, 404, 429):
                    log.warning(
                        "aeroapi_miss",
                        callsign=callsign,
                        status=r.status_code,
                    )
                    return None
                if r.status_code >= 400:
                    log.warning(
                        "aeroapi_http_error",
                        callsign=callsign,
                        status=r.status_code,
                    )
                    return None
                data = r.json()
            except (httpx.HTTPError, ValueError) as e:
                log.warning("aeroapi_fetch_failed", callsign=callsign, error=str(e))
                return None

        flights = (data or {}).get("flights") or []
        # Pick the most recent non-cancelled flight. The list is already in
        # descending-time order per docs; filter cancelled then take first.
        candidate: dict[str, Any] | None = None
        for f in flights:
            if f.get("cancelled"):
                continue
            candidate = f
            break
        if candidate is None and flights:
            candidate = flights[0]
        if candidate is None:
            return None

        origin_raw = candidate.get("origin") or {}
        dest_raw = candidate.get("destination") or {}

        def _airport(raw: dict[str, Any]) -> Airport | None:
            icao = raw.get("code_icao")
            if not icao:
                return None
            return Airport(
                icao=icao,
                iata=raw.get("code_iata"),
                name=raw.get("name") or icao,
                city=raw.get("city"),
            )

        origin = _airport(origin_raw)
        destination = _airport(dest_raw)
        if origin is None and destination is None:
            return None

        airline = candidate.get("operator") or candidate.get("operator_icao")
        return RouteInfo(
            callsign=callsign,
            origin=origin,
            destination=destination,
            airline=airline,
            source="aeroapi",
        )


route_service = RouteService()
