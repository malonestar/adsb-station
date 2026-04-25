"""REST endpoints — /api/*."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from app.alerts.watchlist import watchlist
from app.config import settings
from app.db.models import Alert, AircraftCatalog, RouteCache
from app.db.session import session_scope
from app.enrichment import adsblol
from app.enrichment.coordinator import coordinator as enrichment_coordinator
from app.enrichment.route import route_service
from app.feeds.health import health
from app.history import queries as hq
from app.logging import get_logger
from app.notifications.dispatcher import dispatcher as notification_dispatcher
from app.readsb.poller import ReadsbPoller
from app.stats.live import live_stats

from sqlalchemy import select

log = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["adsb"])


# ── Heatmap response TTL cache ─────────────────────────────────────────
# Full-table aggregation over the positions table is expensive (7d / ALL windows
# scan millions of rows and take 15-20s on a Pi 5). An in-process TTL cache lets
# repeat requests within 5 minutes return instantly. Keyed on (hours, grid) —
# the only two parameters that affect the response.
#
# Per-process only: each uvicorn worker keeps its own dict. That's fine; we run
# a single worker. Don't add Redis.
_HEATMAP_CACHE: dict[tuple[int, float], tuple[float, dict[str, Any]]] = {}
_HEATMAP_TTL_SECONDS = 300.0


def _heatmap_cache_get(hours: int, grid: float) -> dict[str, Any] | None:
    entry = _HEATMAP_CACHE.get((hours, grid))
    if entry is None:
        return None
    expires_at, payload = entry
    if monotonic() > expires_at:
        del _HEATMAP_CACHE[(hours, grid)]
        return None
    return payload


def _heatmap_cache_put(hours: int, grid: float, payload: dict[str, Any]) -> None:
    _HEATMAP_CACHE[(hours, grid)] = (monotonic() + _HEATMAP_TTL_SECONDS, payload)


def _get_poller(request: Request) -> ReadsbPoller:
    poller = getattr(request.app.state, "poller", None)
    if poller is None:
        raise HTTPException(status_code=503, detail="poller_not_started")
    return poller


# ── Airport traffic boards ──────────────────────────────────────────────
# Tunables; mirror the frontend lib/airports.ts knobs.
_AIRPORT_LIST: list[dict[str, Any]] = [
    {"icao": "KDEN", "iata": "DEN", "name": "Denver International",
     "short": "DEN", "lat": 39.8617, "lon": -104.6731, "elev_ft": 5434},
    {"icao": "KAPA", "iata": "APA", "name": "Centennial",
     "short": "APA", "lat": 39.5701, "lon": -104.8493, "elev_ft": 5885},
    {"icao": "KBKF", "iata": None, "name": "Buckley Space Force Base",
     "short": "BKF", "lat": 39.7017, "lon": -104.7517, "elev_ft": 5662},
    {"icao": "KFTG", "iata": None, "name": "Front Range",
     "short": "FTG", "lat": 39.7853, "lon": -104.5436, "elev_ft": 5512},
]
_AIRPORT_RADIUS_NM = 30
_AIRPORT_APPROACH_VS = -300
_AIRPORT_DEPART_VS = 300
_AIRPORT_APPROACH_AGL_MAX = 8000
_AIRPORT_DEPART_AGL_MAX = 10000


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlam = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlam / 2) ** 2
    return 2 * 3440.065 * asin(sqrt(a))


@router.get("/airports/traffic")
async def airports_traffic(request: Request) -> dict[str, Any]:
    """Per-airport approaching/departing buckets, using route data to assign
    aircraft to their actual origin/destination airport when available.

    Falls back to closest-airport-by-distance only when no route data is
    available (callsign missing, or route_cache hasn't resolved it yet).
    Single SQL query joins all live callsigns to the route_cache so we
    don't N+1 per aircraft.
    """
    poller = _get_poller(request)
    states = poller.current()

    # Pull route data for every callsign present in the live registry. One
    # query, indexed lookup. Misses (no row, or `not_found` row) just won't
    # appear in the map and we'll fall back to closest-airport.
    callsigns = [s.flight.strip().upper() for s in states if s.flight and s.flight.strip()]
    routes_by_call: dict[str, RouteCache] = {}
    if callsigns:
        async with session_scope() as s:
            rows = (
                await s.execute(
                    select(RouteCache).where(RouteCache.callsign.in_(callsigns))
                )
            ).scalars().all()
        routes_by_call = {r.callsign: r for r in rows}

    by_icao: dict[str, dict[str, list[dict[str, Any]]]] = {
        a["icao"]: {"approaching": [], "departing": []} for a in _AIRPORT_LIST
    }
    airports_by_icao = {a["icao"]: a for a in _AIRPORT_LIST}

    for st in states:
        if st.lat is None or st.lon is None:
            continue
        callsign = (st.flight or "").strip().upper() or None
        route = routes_by_call.get(callsign) if callsign else None

        # Decide which airport this aircraft "belongs to" and in which bucket.
        # Priority: route data (origin → DEPARTING that airport, destination
        # → APPROACHING that airport). Fall back to closest-airport-within-
        # radius when the route doesn't tell us anything useful.
        target_icao: str | None = None
        bucket: str | None = None
        is_departing = (
            st.baro_rate is not None
            and st.baro_rate >= _AIRPORT_DEPART_VS
        )
        is_approaching = (
            st.baro_rate is not None
            and st.baro_rate <= _AIRPORT_APPROACH_VS
        )

        if route is not None:
            if (
                route.origin_icao
                and route.origin_icao in by_icao
                and is_departing
            ):
                target_icao = route.origin_icao
                bucket = "departing"
            elif (
                route.destination_icao
                and route.destination_icao in by_icao
                and is_approaching
            ):
                target_icao = route.destination_icao
                bucket = "approaching"

        if target_icao is None:
            # Fallback: closest airport in our list, then climb/descend
            # decides bucket. This catches GA aircraft with no route data.
            closest_icao: str | None = None
            closest_dist = float("inf")
            for ap in _AIRPORT_LIST:
                d = _haversine_nm(ap["lat"], ap["lon"], st.lat, st.lon)
                if d < closest_dist:
                    closest_dist = d
                    closest_icao = ap["icao"]
            if closest_icao is None or closest_dist > _AIRPORT_RADIUS_NM:
                continue
            target_icao = closest_icao
            if is_approaching:
                bucket = "approaching"
            elif is_departing:
                bucket = "departing"
            else:
                continue

        if target_icao is None or bucket is None:
            continue
        ap = airports_by_icao[target_icao]
        distance_nm = _haversine_nm(ap["lat"], ap["lon"], st.lat, st.lon)
        if distance_nm > _AIRPORT_RADIUS_NM:
            continue
        agl_ft = st.alt_baro - ap["elev_ft"] if st.alt_baro is not None else None
        if agl_ft is None or agl_ft < -200:
            continue
        # Per-bucket altitude gate (tighter for approach than for departure).
        if bucket == "approaching" and agl_ft > _AIRPORT_APPROACH_AGL_MAX:
            continue
        if bucket == "departing" and agl_ft > _AIRPORT_DEPART_AGL_MAX:
            continue

        movement: dict[str, Any] = {
            "hex": st.hex,
            "callsign": callsign or st.registration or st.hex.upper(),
            "type_code": st.type_code,
            "alt_baro": st.alt_baro,
            "agl_ft": agl_ft,
            "baro_rate": st.baro_rate,
            "gs": st.gs,
            "distance_nm": distance_nm,
            "lat": st.lat,
            "lon": st.lon,
            "track": st.track,
            "origin_icao": route.origin_icao if route else None,
            "destination_icao": route.destination_icao if route else None,
            "from_route_data": route is not None and (
                (bucket == "approaching" and route.destination_icao == target_icao)
                or (bucket == "departing" and route.origin_icao == target_icao)
            ),
        }
        by_icao[target_icao][bucket].append(movement)

    # Sort each bucket by distance ascending — closest first
    for icao in by_icao:
        for bucket in ("approaching", "departing"):
            by_icao[icao][bucket].sort(key=lambda m: m["distance_nm"])

    return {"airports": _AIRPORT_LIST, "by_icao": by_icao}


@router.get("/aircraft/global")
async def aircraft_global(
    request: Request,
    radius_nm: int = Query(200, ge=10, le=400),
) -> dict[str, Any]:
    """Aircraft from adsb.lol within a radius of the station.

    Used by the radar's GLOBAL toggle to show ambient traffic beyond our
    antenna range. Server-side TTL-cached so multiple browser tabs don't
    each hammer adsb.lol. Dedups against our own live registry — there's
    no point rendering an aircraft twice if we're picking it up directly.
    """
    poller = _get_poller(request)
    own_hexes = {s.hex.lower() for s in poller.current()}
    rows = await adsblol.lookup_nearby(
        lat=settings.feeder_lat,
        lon=settings.feeder_lon,
        dist_nm=radius_nm,
    )
    # Strip out aircraft we already track ourselves + any rows missing
    # position data (not renderable as map markers).
    out = [
        r for r in rows
        if r.get("lat") is not None
        and r.get("lon") is not None
        and r.get("hex")
        and r["hex"] not in own_hexes
    ]
    return {
        "radius_nm": radius_nm,
        "count": len(out),
        "aircraft": out,
    }


@router.get("/aircraft/live")
async def aircraft_live(request: Request) -> dict[str, Any]:
    poller = _get_poller(request)
    states = poller.current()
    return {
        "ts": datetime.now(UTC).isoformat(),
        "aircraft": [s.model_dump(mode="json") for s in states],
        "receiver": {
            "lat": settings.feeder_lat,
            "lon": settings.feeder_lon,
            "alt_m": settings.feeder_alt_m,
            "name": settings.feeder_name,
        },
        "tick_count": poller.tick_count,
        "last_tick": poller.last_tick.isoformat() if poller.last_tick else None,
    }


@router.get("/aircraft/trails")
async def aircraft_trails(
    request: Request,
    seconds: int = Query(300, ge=1, le=3600),
) -> dict[str, Any]:
    """Return the last N seconds of positions for every currently-live aircraft.

    Used by the radar's "all trails" overlay. One query, grouped in Python by hex.
    Bounded to aircraft present in the poller's live registry so we don't pull
    stale history for aircraft that left range long ago.

    NOTE: this route is registered BEFORE `/aircraft/{hex_code}` below because
    FastAPI matches routes in registration order — otherwise the path-param route
    would capture "trails" as a hex_code.
    """
    from app.db.models import Position

    poller = _get_poller(request)
    live_hexes = {s.hex for s in poller.current()}
    if not live_hexes:
        return {"seconds": seconds, "aircraft": []}

    cutoff = datetime.now(UTC) - timedelta(seconds=seconds)
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Position)
                .where(Position.hex.in_(live_hexes))
                .where(Position.ts >= cutoff)
                .order_by(Position.hex, Position.ts.asc())
            )
        ).scalars().all()

    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        grouped.setdefault(r.hex, []).append(
            {
                "ts": r.ts.isoformat(),
                "lat": r.lat,
                "lon": r.lon,
                "alt_baro": r.alt_baro,
            }
        )

    return {
        "seconds": seconds,
        "aircraft": [{"hex": h, "points": pts} for h, pts in grouped.items()],
    }


@router.get("/aircraft/{hex_code}/route")
async def aircraft_route(hex_code: str, request: Request) -> dict[str, Any]:
    """Return origin/destination for the aircraft's current callsign.

    On-demand fetch only — this endpoint is hit when the user clicks an
    aircraft on the map. 3-tier fallback with aggressive local cache; see
    `app/enrichment/route.py`.
    """
    hex_code = hex_code.lower()
    poller = _get_poller(request)
    live = next((s for s in poller.current() if s.hex == hex_code), None)
    callsign = live.flight.strip().upper() if (live and live.flight) else None
    if not callsign:
        return {
            "callsign": None,
            "origin": None,
            "destination": None,
            "airline": None,
            "source": "no_callsign",
        }
    try:
        route = await route_service.get_route(callsign)
    except Exception as e:  # noqa: BLE001
        log.exception("route_lookup_error", hex=hex_code, callsign=callsign)
        return {
            "callsign": callsign,
            "origin": None,
            "destination": None,
            "airline": None,
            "source": "unavailable",
            "error": str(e),
        }
    if route is None:
        return {
            "callsign": callsign,
            "origin": None,
            "destination": None,
            "airline": None,
            "source": "not_found",
        }
    return route.to_dict()


@router.get("/aircraft/{hex_code}")
async def aircraft_detail(hex_code: str, request: Request) -> dict[str, Any]:
    hex_code = hex_code.lower()
    poller = _get_poller(request)
    live = next((s for s in poller.current() if s.hex == hex_code), None)

    async with session_scope() as s:
        cat = await s.get(AircraftCatalog, hex_code)
    trail = await hq.recent_trail(hex_code, seconds=300)

    return {
        "hex": hex_code,
        "live": live.model_dump(mode="json") if live else None,
        "catalog": _catalog_row(cat) if cat else None,
        "trail": trail,
    }


@router.get("/catalog")
async def get_catalog(
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    search: str | None = None,
    category: str = "all",
    sort: str = "last_seen",
    sort_dir: str = "desc",
) -> dict[str, Any]:
    return await hq.catalog(
        limit=limit,
        offset=offset,
        search=search,
        category=category,
        sort=sort,
        sort_dir=sort_dir,
    )


@router.get("/catalog/csv")
async def get_catalog_csv(
    search: str | None = None,
    category: str = "all",
    sort: str = "last_seen",
    sort_dir: str = "desc",
) -> Response:
    """CSV export of the catalog with the same filter/sort semantics as /catalog.

    No pagination — returns every row matching the filter (capped at 100k as a
    sanity bound; actual catalog never approaches that). Streams as text/csv
    with a Content-Disposition that prompts a download in the browser.
    """
    result = await hq.catalog(
        limit=100_000,
        offset=0,
        search=search,
        category=category,
        sort=sort,
        sort_dir=sort_dir,
    )
    rows = result["rows"]

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        [
            "hex",
            "registration",
            "type_code",
            "operator",
            "first_seen",
            "last_seen",
            "seen_count",
            "max_alt_ft",
            "max_speed_kt",
            "min_distance_nm",
            "is_military",
            "is_interesting",
            "photo_url",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r["hex"],
                r["registration"] or "",
                r["type_code"] or "",
                r["operator"] or "",
                r["first_seen"] or "",
                r["last_seen"] or "",
                r["seen_count"],
                r["max_alt_ft"] if r["max_alt_ft"] is not None else "",
                r["max_speed_kt"] if r["max_speed_kt"] is not None else "",
                f"{r['min_distance_nm']:.2f}" if r["min_distance_nm"] is not None else "",
                "true" if r["is_military"] else "false",
                "true" if r["is_interesting"] else "false",
                r["photo_url"] or "",
            ]
        )

    filename = f"catalog-{datetime.now(UTC).strftime('%Y%m%d-%H%M')}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/stats/live")
async def stats_live(request: Request) -> dict[str, Any]:
    poller = _get_poller(request)
    return live_stats.snapshot(poller.current(), datetime.now(UTC))


@router.get("/stats/aggregates")
async def stats_aggregates(days: int = Query(7, ge=1, le=365)) -> dict[str, Any]:
    from app.db.models import DailyAggregate

    cutoff = (datetime.now(UTC) - timedelta(days=days)).date().isoformat()
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(DailyAggregate)
                .where(DailyAggregate.date >= cutoff)
                .order_by(DailyAggregate.date.desc())
            )
        ).scalars().all()
    return {
        "rows": [
            {
                "date": r.date,
                "msgs_total": r.msgs_total,
                "aircraft_unique": r.aircraft_unique,
                "max_range_nm": r.max_range_nm,
                "top_aircraft": r.top_aircraft_json,
            }
            for r in rows
        ]
    }


@router.get("/history/heatmap")
async def heatmap(hours: int = Query(24, ge=1, le=744), grid: float = 0.02) -> dict[str, Any]:
    # Upper bound 744h = 31 days, matching the positions-table retention window.
    cached = _heatmap_cache_get(hours, grid)
    if cached is not None:
        log.info("heatmap_cache_hit", hours=hours, grid=grid)
        return cached
    result: dict[str, Any] = {
        "grid": grid,
        "hours": hours,
        "bins": await hq.heatmap(hours=hours, grid=grid),
    }
    _heatmap_cache_put(hours, grid, result)
    return result


@router.get("/history/replay")
async def replay(
    start: datetime,
    end: datetime,
    hex_code: str | None = Query(None, alias="hex"),
) -> dict[str, Any]:
    return {"rows": await hq.replay(start, end, hex_code=hex_code)}


@router.get("/alerts/live")
async def alerts_live() -> dict[str, Any]:
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Alert, AircraftCatalog)
                .outerjoin(AircraftCatalog, AircraftCatalog.hex == Alert.hex)
                .where(Alert.cleared_at.is_(None))
                .order_by(Alert.triggered_at.desc())
            )
        ).all()
    return {"alerts": [_alert_row(a, c) for a, c in rows]}


@router.get("/alerts")
async def alerts_history(limit: int = Query(100, le=500)) -> dict[str, Any]:
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Alert, AircraftCatalog)
                .outerjoin(AircraftCatalog, AircraftCatalog.hex == Alert.hex)
                .order_by(Alert.triggered_at.desc())
                .limit(limit)
            )
        ).all()
    return {"alerts": [_alert_row(a, c) for a, c in rows]}


class AlertTestRequest(BaseModel):
    channel: Literal["telegram", "discord", "email", "all"] = "all"


@router.post("/alerts/test")
async def alerts_test(body: AlertTestRequest | None = None) -> dict[str, Any]:
    """Fire a synthetic alert through the selected channel(s).

    POST body: {"channel": "telegram" | "discord" | "email" | "all"}
    Empty body defaults to {"channel": "all"}.

    Returns a per-channel status dict from the dispatcher's test_send().
    """
    channel = body.channel if body is not None else "all"
    try:
        results = await notification_dispatcher.test_send(channel=channel)
    except Exception as e:  # noqa: BLE001
        log.exception("alerts_test_failed", channel=channel)
        raise HTTPException(status_code=500, detail=f"test_send failed: {e!r}") from e
    return {"channel": channel, "results": results}


@router.get("/watchlist")
async def watchlist_list() -> dict[str, Any]:
    rows = await watchlist.all()
    return {
        "entries": [
            {
                "id": r.id,
                "kind": r.kind,
                "value": r.value,
                "label": r.label,
                "notify": r.notify,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.post("/watchlist")
async def watchlist_add(body: dict[str, Any]) -> dict[str, Any]:
    kind = body.get("kind")
    value = body.get("value")
    label = body.get("label")
    # Honor an explicit notify flag if the caller sent one; otherwise let the
    # store apply the kind-aware default (hex=True, others=False).
    notify_raw = body.get("notify")
    notify: bool | None = bool(notify_raw) if notify_raw is not None else None
    if not kind or not value:
        raise HTTPException(status_code=400, detail="kind and value required")
    row = await watchlist.add(kind=kind, value=value, label=label, notify=notify)
    # Cold-enrich hex entries whose aircraft we've never seen — fills in
    # registration / type / operator / photo so the watchlist tab is
    # immediately useful even before the aircraft transits range.
    if kind.lower() == "hex":
        async with session_scope() as s:
            existing = await s.get(AircraftCatalog, value.lower())
        if existing is None:
            await enrichment_coordinator.enrich_cold(value)
    return {
        "id": row.id, "kind": row.kind, "value": row.value,
        "label": row.label, "notify": row.notify,
    }


@router.patch("/watchlist/{entry_id}")
async def watchlist_update(entry_id: int, body: dict[str, Any]) -> dict[str, Any]:
    """Toggle the notify flag on an existing entry (no remove + re-add needed)."""
    if "notify" not in body:
        raise HTTPException(status_code=400, detail="notify field required")
    row = await watchlist.set_notify(entry_id, bool(body["notify"]))
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "id": row.id, "kind": row.kind, "value": row.value,
        "label": row.label, "notify": row.notify,
    }


@router.delete("/watchlist/{entry_id}")
async def watchlist_delete(entry_id: int) -> dict[str, Any]:
    deleted = await watchlist.remove(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="not found")
    return {"deleted": True}


@router.get("/watchlist/details")
async def watchlist_details(request: Request) -> dict[str, Any]:
    """Joined view for the Watchlist tab — entry + catalog + live status."""
    poller = _get_poller(request)
    live_hexes = {s.hex.lower() for s in poller.current()}
    entries = await watchlist.all()
    if not entries:
        return {"items": []}

    hex_values = [e.value.lower() for e in entries if e.kind == "hex"]
    catalog_by_hex: dict[str, AircraftCatalog] = {}
    if hex_values:
        async with session_scope() as s:
            rows = (
                await s.execute(
                    select(AircraftCatalog).where(AircraftCatalog.hex.in_(hex_values))
                )
            ).scalars().all()
        catalog_by_hex = {r.hex: r for r in rows}

    items: list[dict[str, Any]] = []
    for e in entries:
        item: dict[str, Any] = {
            "id": e.id,
            "kind": e.kind,
            "value": e.value,
            "label": e.label,
            "notify": e.notify,
            "created_at": e.created_at.isoformat(),
            "live": False,
            "catalog": None,
        }
        if e.kind == "hex":
            hex_lc = e.value.lower()
            item["live"] = hex_lc in live_hexes
            row = catalog_by_hex.get(hex_lc)
            if row is not None:
                ever_seen = row.seen_count > 0
                item["catalog"] = {
                    "registration": row.registration,
                    "type_code": row.type_code,
                    "operator": row.operator,
                    "photo_url": row.photo_url,
                    "photo_thumb_url": row.photo_thumb_url,
                    "photo_link": row.photo_link,
                    "is_military": row.is_military,
                    "is_interesting": row.is_interesting,
                    "first_seen": row.first_seen.isoformat() if ever_seen else None,
                    "last_seen": row.last_seen.isoformat() if ever_seen else None,
                    "seen_count": row.seen_count,
                    "max_alt_ft": row.max_alt_ft,
                    "max_speed_kt": row.max_speed_kt,
                    "min_distance_nm": row.min_distance_nm,
                }
        items.append(item)
    return {"items": items}


@router.get("/feeds/health")
async def feeds_health() -> dict[str, Any]:
    return {"feeds": health.current()}


@router.get("/receiver")
async def receiver_info() -> dict[str, Any]:
    return {
        "lat": settings.feeder_lat,
        "lon": settings.feeder_lon,
        "alt_m": settings.feeder_alt_m,
        "name": settings.feeder_name,
        "tz": settings.feeder_tz,
    }


# ─── helpers ────────────────────────────────────────────────────────────


def _catalog_row(r: AircraftCatalog) -> dict[str, Any]:
    return {
        "hex": r.hex,
        "registration": r.registration,
        "type_code": r.type_code,
        "operator": r.operator,
        "owner": r.owner,
        "country": r.country,
        "category": r.category,
        "first_seen": r.first_seen.isoformat() if r.first_seen else None,
        "last_seen": r.last_seen.isoformat() if r.last_seen else None,
        "seen_count": r.seen_count,
        "max_alt_ft": r.max_alt_ft,
        "max_speed_kt": r.max_speed_kt,
        "min_distance_nm": r.min_distance_nm,
        "is_military": r.is_military,
        "is_interesting": r.is_interesting,
        "is_pia": r.is_pia,
        "photo_url": r.photo_url,
        "photo_thumb_url": r.photo_thumb_url,
        "photo_photographer": r.photo_photographer,
        "photo_link": r.photo_link,
    }


def _alert_row(r: Alert, catalog: AircraftCatalog | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": r.id,
        "hex": r.hex,
        "kind": r.kind,
        "triggered_at": r.triggered_at.isoformat(),
        "cleared_at": r.cleared_at.isoformat() if r.cleared_at else None,
        "payload": r.payload,
        "catalog": None,
    }
    if catalog is not None:
        out["catalog"] = {
            "registration": catalog.registration,
            "type_code": catalog.type_code,
            "operator": catalog.operator,
            "photo_url": catalog.photo_url,
            "photo_thumb_url": catalog.photo_thumb_url,
            "is_military": catalog.is_military,
            "is_interesting": catalog.is_interesting,
        }
    return out
