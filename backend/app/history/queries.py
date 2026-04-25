"""Historical queries — catalog, trails, heatmap, replay."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from collections import defaultdict

from sqlalchemy import and_, exists, func, or_, select, text

from app.db.models import AircraftCatalog, Alert, Position, Watchlist
from app.db.session import session_scope

# Pre-aggregation grid used by the position_cells_hourly rollup. The rollup
# fast-path is only consulted when the heatmap request asks for this same
# grid; other values fall through to the live aggregation.
_HEATMAP_ROLLUP_GRID = 0.02


# Catalog sort — whitelist of (column expression, default direction) keyed by external name.
# Using a whitelist prevents SQL injection via the `sort` query param and pins
# known-safe column references.
_CATALOG_SORT_COLUMNS = {
    "last_seen": AircraftCatalog.last_seen,
    "first_seen": AircraftCatalog.first_seen,
    "seen_count": AircraftCatalog.seen_count,
    "max_alt_ft": AircraftCatalog.max_alt_ft,
    "max_speed_kt": AircraftCatalog.max_speed_kt,
    "min_distance_nm": AircraftCatalog.min_distance_nm,
    "registration": AircraftCatalog.registration,
}

_CATALOG_CATEGORIES = {
    "all",
    "military",
    "interesting",
    "has_photo",
    "seen_last_hour",
    "watchlist",
    "emergency_recent",
}


async def recent_trail(hex_code: str, seconds: int = 120) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(seconds=seconds)
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(Position)
                .where(and_(Position.hex == hex_code, Position.ts >= cutoff))
                .order_by(Position.ts.asc())
            )
        ).scalars().all()
    return [
        {
            "ts": r.ts.isoformat(),
            "lat": r.lat,
            "lon": r.lon,
            "alt_baro": r.alt_baro,
            "gs": r.gs,
            "track": r.track,
            "baro_rate": r.baro_rate,
        }
        for r in rows
    ]


async def replay(
    start: datetime,
    end: datetime,
    hex_code: str | None = None,
) -> list[dict[str, Any]]:
    async with session_scope() as s:
        stmt = select(Position).where(Position.ts >= start, Position.ts <= end)
        if hex_code:
            stmt = stmt.where(Position.hex == hex_code)
        stmt = stmt.order_by(Position.ts.asc())
        rows = (await s.execute(stmt)).scalars().all()
    return [
        {
            "hex": r.hex,
            "ts": r.ts.isoformat(),
            "lat": r.lat,
            "lon": r.lon,
            "alt_baro": r.alt_baro,
            "gs": r.gs,
            "track": r.track,
        }
        for r in rows
    ]


async def heatmap(hours: int = 24, grid: float = 0.02) -> list[dict[str, Any]]:
    """Heatmap aggregation. Routes through the rollup table for the default grid.

    For the canonical grid=0.02° we read the pre-aggregated `position_cells_hourly`
    table for any hour bucket that has been completed and rolled up, plus a live
    aggregation over the trailing hour (which the cron hasn't summarized yet).
    Any other grid value falls back to the live full-positions aggregation.
    """
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=hours)

    if grid != _HEATMAP_ROLLUP_GRID:
        return await _heatmap_live(cutoff, grid=grid)

    # Boundary: rollup covers fully-elapsed hours up to the start of the
    # CURRENT hour. The current (partial) hour is never rolled up by the
    # cron, so we always merge it from live positions.
    current_hour_start = now.replace(minute=0, second=0, microsecond=0)
    cutoff_bucket = cutoff.strftime("%Y-%m-%dT%H")

    async with session_scope() as s:
        rollup_rows = (
            await s.execute(
                text(
                    """
                    SELECT lat_cell, lon_cell, SUM(count) AS n
                    FROM position_cells_hourly
                    WHERE hour_bucket >= :cutoff_bucket
                    GROUP BY lat_cell, lon_cell
                    """
                ),
                {"cutoff_bucket": cutoff_bucket},
            )
        ).all()

    # Partial trailing hour — small live aggregation (typically <30s on a Pi).
    live_rows = await _heatmap_live(current_hour_start, grid=grid)

    merged: dict[tuple[float, float], int] = defaultdict(int)
    for lat, lon, n in rollup_rows:
        merged[(lat, lon)] += int(n)
    for r in live_rows:
        merged[(r["lat"], r["lon"])] += int(r["count"])
    return [{"lat": lat, "lon": lon, "count": c} for (lat, lon), c in merged.items()]


async def _heatmap_live(
    cutoff: datetime, *, grid: float = _HEATMAP_ROLLUP_GRID
) -> list[dict[str, Any]]:
    """Aggregate from the live positions table (fallback / trailing-hour path).

    NOTE: `.group_by(lat_expr, lon_expr)` must pass the expressions themselves —
    using string labels would match the raw Position.lat/lon columns instead and
    leave you with millions of near-unique points.
    """
    async with session_scope() as s:
        lat_expr = (func.round(Position.lat / grid) * grid).label("lat")
        lon_expr = (func.round(Position.lon / grid) * grid).label("lon")
        rows = (
            await s.execute(
                select(lat_expr, lon_expr, func.count().label("n"))
                .where(Position.ts >= cutoff)
                .group_by(lat_expr, lon_expr)
            )
        ).all()
    return [{"lat": r.lat, "lon": r.lon, "count": r.n} for r in rows]


async def catalog(
    limit: int = 100,
    offset: int = 0,
    search: str | None = None,
    category: str = "all",
    sort: str = "last_seen",
    sort_dir: str = "desc",
) -> dict[str, Any]:
    """Catalog listing with search, category filter, and column sort.

    Categories:
        all, military, interesting, has_photo, seen_last_hour, watchlist, emergency_recent
    Sort columns:
        last_seen, first_seen, seen_count, max_alt_ft, max_speed_kt,
        min_distance_nm, registration
    Invalid values fall back to the defaults rather than erroring, so a stale client
    query string doesn't hard-break the page.
    """
    now = datetime.now(UTC)
    async with session_scope() as s:
        stmt = select(AircraftCatalog)

        if search:
            like = f"%{search.lower()}%"
            stmt = stmt.where(
                (func.lower(AircraftCatalog.registration).like(like))
                | (func.lower(AircraftCatalog.type_code).like(like))
                | (func.lower(AircraftCatalog.hex).like(like))
                | (func.lower(AircraftCatalog.operator).like(like))
            )

        cat = category if category in _CATALOG_CATEGORIES else "all"
        if cat == "military":
            stmt = stmt.where(AircraftCatalog.is_military.is_(True))
        elif cat == "interesting":
            stmt = stmt.where(AircraftCatalog.is_interesting.is_(True))
        elif cat == "has_photo":
            stmt = stmt.where(AircraftCatalog.photo_url.is_not(None))
        elif cat == "seen_last_hour":
            stmt = stmt.where(AircraftCatalog.last_seen >= now - timedelta(hours=1))
        elif cat == "watchlist":
            # Aircraft that match ANY watchlist entry by one of the supported kinds.
            stmt = stmt.where(
                exists().where(
                    or_(
                        and_(Watchlist.kind == "hex", Watchlist.value == AircraftCatalog.hex),
                        and_(
                            Watchlist.kind == "reg",
                            Watchlist.value == AircraftCatalog.registration,
                        ),
                        and_(
                            Watchlist.kind == "type",
                            Watchlist.value == AircraftCatalog.type_code,
                        ),
                        and_(
                            Watchlist.kind == "operator",
                            Watchlist.value == AircraftCatalog.operator,
                        ),
                    )
                )
            )
        elif cat == "emergency_recent":
            cutoff = now - timedelta(hours=24)
            stmt = stmt.where(
                exists().where(
                    and_(
                        Alert.hex == AircraftCatalog.hex,
                        Alert.kind == "emergency",
                        Alert.triggered_at >= cutoff,
                    )
                )
            )

        total = (await s.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0

        sort_col = _CATALOG_SORT_COLUMNS.get(sort, AircraftCatalog.last_seen)
        order = sort_col.desc() if sort_dir.lower() != "asc" else sort_col.asc()
        # NULLs at the end regardless of direction — e.g., seen_count has no NULLs
        # but max_alt_ft / min_distance_nm / registration do, and empty cells shouldn't
        # rise to the top of a descending sort.
        stmt = stmt.order_by(order.nulls_last()).limit(limit).offset(offset)
        rows = (await s.execute(stmt)).scalars().all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "sort": sort if sort in _CATALOG_SORT_COLUMNS else "last_seen",
        "sort_dir": "asc" if sort_dir.lower() == "asc" else "desc",
        "category": cat,
        "rows": [
            {
                "hex": r.hex,
                "registration": r.registration,
                "type_code": r.type_code,
                "operator": r.operator,
                "category": r.category,
                "first_seen": r.first_seen.isoformat() if r.first_seen else None,
                "last_seen": r.last_seen.isoformat() if r.last_seen else None,
                "seen_count": r.seen_count,
                "max_alt_ft": r.max_alt_ft,
                "max_speed_kt": r.max_speed_kt,
                "min_distance_nm": r.min_distance_nm,
                "is_military": r.is_military,
                "is_interesting": r.is_interesting,
                "photo_url": r.photo_url,
                "photo_thumb_url": r.photo_thumb_url,
            }
            for r in rows
        ],
    }
