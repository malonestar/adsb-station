"""Daily rollup via APScheduler cron."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import AircraftCatalog, DailyAggregate, Position
from app.db.session import session_scope
from app.logging import get_logger
from app.readsb.parser import haversine_nm

log = get_logger(__name__)

scheduler = AsyncIOScheduler()


async def _compute_max_range_nm(
    s: AsyncSession, start: datetime, end: datetime
) -> float:
    """Max haversine distance (nm) from station to any Position in [start, end)."""
    rows = await s.execute(
        select(Position.lat, Position.lon).where(
            Position.ts >= start, Position.ts < end
        )
    )
    max_range = 0.0
    for lat, lon in rows:
        d = haversine_nm(settings.feeder_lat, settings.feeder_lon, lat, lon)
        if d > max_range:
            max_range = d
    return max_range


async def _rollup_for_date(d: date) -> None:
    """Compute the daily aggregate row for a single UTC date."""
    start = datetime.combine(d, datetime.min.time()).replace(tzinfo=UTC)
    end = start + timedelta(days=1)

    async with session_scope() as s:
        msgs = (
            await s.execute(
                select(func.count(Position.id)).where(
                    Position.ts >= start, Position.ts < end
                )
            )
        ).scalar() or 0
        unique = (
            await s.execute(
                select(func.count(func.distinct(Position.hex))).where(
                    Position.ts >= start, Position.ts < end
                )
            )
        ).scalar() or 0
        top = (
            await s.execute(
                select(Position.hex, func.count(Position.id).label("n"))
                .where(Position.ts >= start, Position.ts < end)
                .group_by(Position.hex)
                .order_by(func.count(Position.id).desc())
                .limit(5)
            )
        ).all()
        top_json = [{"hex": r.hex, "count": r.n} for r in top]
        max_range_nm = await _compute_max_range_nm(s, start, end)

        existing = await s.get(DailyAggregate, d.isoformat())
        if existing:
            existing.msgs_total = msgs
            existing.aircraft_unique = unique
            existing.max_range_nm = max_range_nm
            existing.top_aircraft_json = {"top": top_json}
        else:
            s.add(
                DailyAggregate(
                    date=d.isoformat(),
                    msgs_total=msgs,
                    aircraft_unique=unique,
                    max_range_nm=max_range_nm,
                    top_aircraft_json={"top": top_json},
                )
            )
    log.info(
        "daily_rollup_complete",
        date=d.isoformat(),
        msgs=msgs,
        unique=unique,
        max_range_nm=round(max_range_nm, 1),
    )


async def rollup_yesterday() -> None:
    """Compute yesterday's aggregate row."""
    yesterday = (datetime.now(UTC) - timedelta(days=1)).date()
    await _rollup_for_date(yesterday)


async def backfill_max_range_all() -> None:
    """One-shot: re-roll every day that has positions, populating max_range_nm.

    Safe to run repeatedly — re-computes msgs/unique/top from the same source rows,
    so values match what the daily cron would have produced.
    """
    async with session_scope() as s:
        rows = (
            await s.execute(
                select(func.distinct(func.date(Position.ts))).order_by(
                    func.date(Position.ts)
                )
            )
        ).scalars().all()
    dates: list[date] = [
        date.fromisoformat(r) if isinstance(r, str) else r for r in rows
    ]
    log.info("backfill_max_range_start", days=len(dates))
    for d in dates:
        await _rollup_for_date(d)
    log.info("backfill_max_range_complete", days=len(dates))


async def prune_old_positions() -> None:
    """Enforce retention policy on the positions table."""
    cutoff = datetime.now(UTC) - timedelta(days=settings.position_retention_days)
    async with session_scope() as s:
        r = await s.execute(delete(Position).where(Position.ts < cutoff))
        log.info("positions_pruned", count=r.rowcount or 0, cutoff=cutoff.isoformat())


async def purge_enrichment() -> None:
    from app.enrichment.cache import cache

    n = await cache.purge_expired()
    if n:
        log.info("enrichment_purged", count=n)


def configure_jobs() -> None:
    # Daily rollup at 00:05 UTC
    scheduler.add_job(
        rollup_yesterday,
        CronTrigger(hour=0, minute=5, timezone="UTC"),
        id="daily_rollup",
        replace_existing=True,
    )
    # Position retention prune daily at 03:15 UTC
    scheduler.add_job(
        prune_old_positions,
        CronTrigger(hour=3, minute=15, timezone="UTC"),
        id="prune_positions",
        replace_existing=True,
    )
    # Enrichment cache GC every 6 hours
    scheduler.add_job(
        purge_enrichment,
        CronTrigger(hour="*/6", minute=30, timezone="UTC"),
        id="purge_enrichment",
        replace_existing=True,
    )
