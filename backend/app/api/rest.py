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
from app.db.models import Alert, AircraftCatalog
from app.db.session import session_scope
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
