"""Tests for the position_cells_hourly heatmap rollup.

Covers:
- rollup_position_cells_hour aggregates the right window
- backfill_position_cells_all enumerates all hours present
- heatmap() merges rollup with the live trailing-hour query
- Idempotent re-runs do not double-count
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import Base, Position
from app.history import queries as hq
from app.stats import aggregates as agg


@pytest.fixture
async def memdb(monkeypatch):
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

    # Both modules read session_scope via their own imports.
    monkeypatch.setattr(agg, "session_scope", fake_scope)
    monkeypatch.setattr(hq, "session_scope", fake_scope)
    try:
        yield Session
    finally:
        await engine.dispose()


def _seed_positions(session_factory):
    """Insert a synthetic mix of positions across multiple hours."""
    return session_factory


async def test_rollup_one_hour_aggregates_into_cells(memdb):
    """Single hour rollup produces correct per-cell counts."""
    base = datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC)
    async with memdb() as s:
        # 3 positions in the same 0.02° cell (lat 39.70, lon -104.80) at 12:00
        for i in range(3):
            s.add(Position(hex="aaa001", ts=base + timedelta(seconds=i),
                           lat=39.7001 + i * 0.0001, lon=-104.8001))
        # 2 positions in a different cell (lat 40.00, lon -104.00)
        for i in range(2):
            s.add(Position(hex="bbb002", ts=base + timedelta(minutes=10 + i),
                           lat=40.0, lon=-104.0))
        # 1 position in the NEXT hour — must NOT appear in this rollup
        s.add(Position(hex="ccc003", ts=base + timedelta(hours=1, minutes=5),
                       lat=39.5, lon=-104.5))
        await s.commit()

    inserted = await agg.rollup_position_cells_hour(base)
    assert inserted == 2  # 2 distinct cells in this hour

    async with memdb() as s:
        rows = (
            await s.execute(
                text("SELECT hour_bucket, lat_cell, lon_cell, count FROM position_cells_hourly ORDER BY count DESC")
            )
        ).all()
    assert len(rows) == 2
    assert rows[0].count == 3 and rows[0].hour_bucket == "2026-04-24T12"
    assert rows[1].count == 2


async def test_rollup_is_idempotent(memdb):
    """Re-running the same hour overwrites instead of double-counting."""
    base = datetime(2026, 4, 24, 12, 0, 0, tzinfo=UTC)
    async with memdb() as s:
        s.add(Position(hex="aaa001", ts=base, lat=39.7, lon=-104.8))
        await s.commit()
    await agg.rollup_position_cells_hour(base)
    await agg.rollup_position_cells_hour(base)  # idempotent re-run

    async with memdb() as s:
        rows = (
            await s.execute(text("SELECT count FROM position_cells_hourly"))
        ).all()
    assert len(rows) == 1
    assert rows[0].count == 1, "Re-run must overwrite, not double-count"


async def test_backfill_covers_every_hour(memdb):
    """Backfill enumerates DISTINCT hours from positions and rolls each up."""
    base = datetime(2026, 4, 24, 10, 0, 0, tzinfo=UTC)
    async with memdb() as s:
        for hour in (10, 11, 12):
            for i in range(2):
                s.add(Position(
                    hex="aaa001",
                    ts=base.replace(hour=hour) + timedelta(minutes=i * 5),
                    lat=39.7, lon=-104.8,
                ))
        await s.commit()

    await agg.backfill_position_cells_all()

    async with memdb() as s:
        rows = (
            await s.execute(
                text("SELECT hour_bucket, count FROM position_cells_hourly ORDER BY hour_bucket")
            )
        ).all()
    buckets = [r.hour_bucket for r in rows]
    assert buckets == ["2026-04-24T10", "2026-04-24T11", "2026-04-24T12"]
    assert all(r.count == 2 for r in rows)


async def test_heatmap_merges_rollup_and_trailing_live(memdb, monkeypatch):
    """heatmap() must combine rollup data with the current incomplete hour."""
    # Anchor "now" so we can deterministically split rolled-up vs live data.
    fixed_now = datetime(2026, 4, 25, 14, 30, 0, tzinfo=UTC)
    current_hour_start = fixed_now.replace(minute=0, second=0, microsecond=0)

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr(hq, "datetime", FakeDateTime)

    async with memdb() as s:
        # Rolled-up hour: 13:00 — 4 positions in cell (39.70, -104.80)
        for i in range(4):
            s.add(Position(
                hex="aaa001",
                ts=current_hour_start - timedelta(hours=1) + timedelta(minutes=i),
                lat=39.7, lon=-104.8,
            ))
        # Trailing live hour: 14:00 — 3 positions in the SAME cell
        for i in range(3):
            s.add(Position(
                hex="aaa001",
                ts=current_hour_start + timedelta(minutes=i),
                lat=39.7, lon=-104.8,
            ))
        await s.commit()

    # Roll up the 13:00 hour but NOT the 14:00 partial hour
    await agg.rollup_position_cells_hour(current_hour_start - timedelta(hours=1))

    bins = await hq.heatmap(hours=2, grid=0.02)
    assert len(bins) == 1
    assert bins[0]["count"] == 7  # 4 rolled + 3 live, merged on the same cell


async def test_heatmap_falls_back_to_live_for_nonstandard_grid(memdb, monkeypatch):
    """A grid != 0.02 must bypass the rollup and use the requested grid."""
    base = datetime.now(UTC) - timedelta(hours=1)
    async with memdb() as s:
        # Two points that share a 0.5° cell — same rounded (39.5, -105.0)
        s.add(Position(hex="aaa001", ts=base, lat=39.55, lon=-104.85))
        s.add(Position(hex="aaa001", ts=base + timedelta(seconds=1),
                       lat=39.65, lon=-104.95))
        # And one point in a DIFFERENT 0.5° cell — (40.0, -105.0)
        s.add(Position(hex="bbb002", ts=base + timedelta(seconds=2),
                       lat=39.95, lon=-104.95))
        await s.commit()
    # No rollup ran — but with grid=0.5, live path is used.
    bins = await hq.heatmap(hours=2, grid=0.5)
    bins_by_cell = {(b["lat"], b["lon"]): b["count"] for b in bins}
    assert bins_by_cell[(39.5, -105.0)] == 2
    assert bins_by_cell[(40.0, -105.0)] == 1
