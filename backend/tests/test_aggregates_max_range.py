"""Tests for daily_aggregates.max_range_nm population.

Regression: the rollup hardcoded max_range_nm=0.0 in the INSERT path and
omitted it entirely from the UPDATE path, so /api/stats/aggregates always
returned 0.0 for every day. Fix computes max haversine distance from
Position rows in the day's window.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Base, DailyAggregate, Position
from app.stats import aggregates as aggregates_module


@pytest.fixture
async def memdb(monkeypatch):
    """In-memory SQLite bound to app.stats.aggregates.session_scope."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def fake_scope():
        async with Session() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    monkeypatch.setattr(aggregates_module, "session_scope", fake_scope)
    monkeypatch.setattr(aggregates_module.settings, "feeder_lat", 39.7)
    monkeypatch.setattr(aggregates_module.settings, "feeder_lon", -104.8)
    try:
        yield Session
    finally:
        await engine.dispose()


def _yesterday_noon() -> tuple[str, datetime]:
    yest = (datetime.now(UTC) - timedelta(days=1)).date()
    base = datetime.combine(yest, datetime.min.time()).replace(tzinfo=UTC)
    return yest.isoformat(), base + timedelta(hours=12)


async def test_rollup_insert_populates_max_range_nm(memdb):
    """Fresh INSERT path must compute max_range_nm from positions."""
    yest_iso, noon = _yesterday_noon()

    async with memdb() as s:
        # Station is (39.7, -104.8). Three positions, varying distance.
        s.add(Position(hex="aaa001", ts=noon, lat=40.2, lon=-104.8))                 # ~30 nm N
        s.add(Position(hex="bbb002", ts=noon + timedelta(minutes=5), lat=39.7, lon=-102.2))  # ~120 nm E (max)
        s.add(Position(hex="ccc003", ts=noon + timedelta(minutes=10), lat=38.9, lon=-104.8)) # ~48 nm S
        await s.commit()

    await aggregates_module.rollup_yesterday()

    async with memdb() as s:
        row = (await s.execute(select(DailyAggregate))).scalar_one()
    assert row.date == yest_iso
    # 2.6° east at 39.7°N = 2.6*60*cos(39.7°) ≈ 120.0 nm
    assert 119.0 < row.max_range_nm < 121.0, f"got {row.max_range_nm}"


async def test_rollup_update_overwrites_stale_max_range_nm(memdb):
    """Re-running rollup with an existing 0.0 row must overwrite max_range_nm."""
    yest_iso, noon = _yesterday_noon()

    async with memdb() as s:
        # Pre-existing row left over from the buggy rollup
        s.add(DailyAggregate(date=yest_iso, msgs_total=0, aircraft_unique=0, max_range_nm=0.0))
        s.add(Position(hex="aaa001", ts=noon, lat=39.7, lon=-102.2))  # ~120 nm E
        await s.commit()

    await aggregates_module.rollup_yesterday()

    async with memdb() as s:
        row = (await s.execute(select(DailyAggregate))).scalar_one()
    assert 119.0 < row.max_range_nm < 121.0, f"got {row.max_range_nm}"


async def test_rollup_isolates_to_target_day(memdb):
    """Positions outside yesterday's window must not affect max_range_nm."""
    yest_iso, noon = _yesterday_noon()

    async with memdb() as s:
        # Yesterday: only a close-in position
        s.add(Position(hex="aaa001", ts=noon, lat=40.2, lon=-104.8))  # ~30 nm
        # Two days ago: a very far one — must NOT count
        s.add(Position(hex="zzz999", ts=noon - timedelta(days=1), lat=39.7, lon=-99.0))  # ~270 nm
        # Today: another far one — also must not count
        s.add(Position(hex="yyy888", ts=noon + timedelta(days=1), lat=39.7, lon=-99.0))
        await s.commit()

    await aggregates_module.rollup_yesterday()

    async with memdb() as s:
        row = (await s.execute(select(DailyAggregate))).scalar_one()
    # Should be ~30, definitely not the 270 nm decoy
    assert row.max_range_nm < 50.0, f"leaked from another day: {row.max_range_nm}"
    assert row.max_range_nm > 25.0, f"yesterday's 30nm position lost: {row.max_range_nm}"


async def test_rollup_empty_day_zero_range(memdb):
    """A day with no positions must yield max_range_nm == 0.0."""
    await aggregates_module.rollup_yesterday()
    async with memdb() as s:
        row = (await s.execute(select(DailyAggregate))).scalar_one()
    assert row.max_range_nm == 0.0
