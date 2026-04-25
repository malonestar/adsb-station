"""Tests for the alert re-open-within-grace behavior.

Regression: aircraft a70116 produced 9 high_altitude rows in 24 minutes because
brief ADS-B signal dropouts were causing the evaluator to clear → re-insert
a new row on the next reappearance. The fix: on trigger, if the most recent
row for the same (hex, kind) was cleared within REOPEN_WINDOW, re-use it
(null its cleared_at) instead of inserting a new row.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.alerts import rules as rules_module
from app.alerts.rules import AlertEvaluator
from app.config import settings
from app.db.models import Alert, Base
from app.readsb.schema import AircraftState


@pytest.fixture
async def memdb(monkeypatch):
    """In-memory SQLite bound to app.alerts.rules.session_scope."""
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

    monkeypatch.setattr(rules_module, "session_scope", fake_scope)

    # Also swallow bus.publish so we don't need a running event loop bus.
    async def noop_publish(*args, **kwargs):
        return None

    monkeypatch.setattr(rules_module.bus, "publish", noop_publish)
    # Prevent watchlist.refresh() from hitting the DB in start().
    async def noop_refresh():
        return None

    monkeypatch.setattr(rules_module.watchlist, "refresh", noop_refresh)

    try:
        yield Session
    finally:
        await engine.dispose()


def _mk(hex_code: str, alt: int | None) -> AircraftState:
    return AircraftState(hex=hex_code, alt_baro=alt, updated_at=datetime.now(UTC))


async def test_trigger_clear_trigger_within_grace_reopens_row(memdb):
    """Trigger → clear → trigger within REOPEN_WINDOW = 1 row, re-opened."""
    ev = AlertEvaluator()
    await ev.start()
    state = _mk("a70116", settings.alert_high_altitude_ft + 1000)

    # First trigger inserts a new row.
    await ev._trigger(state, "high_altitude")
    # Clear writes cleared_at.
    await ev._clear(state.hex, "high_altitude")
    # Second trigger within REOPEN_WINDOW should re-open, not insert.
    await ev._trigger(state, "high_altitude")

    async with memdb() as s:
        rows = (await s.execute(select(Alert).order_by(Alert.id))).scalars().all()

    assert len(rows) == 1, f"expected 1 row (re-opened), got {len(rows)}"
    assert rows[0].cleared_at is None, "re-opened row should have cleared_at=NULL"
    assert (state.hex, "high_altitude") in ev._active


async def test_trigger_clear_trigger_after_window_inserts_new_row(memdb):
    """After REOPEN_WINDOW expires, a new trigger should insert a new row."""
    ev = AlertEvaluator()
    await ev.start()
    state = _mk("a70116", settings.alert_high_altitude_ft + 1000)

    await ev._trigger(state, "high_altitude")
    await ev._clear(state.hex, "high_altitude")

    # Back-date the cleared_at to be older than REOPEN_WINDOW so the next
    # trigger falls outside the re-open path.
    from sqlalchemy import update as sa_update

    past = datetime.now(UTC) - ev.REOPEN_WINDOW - timedelta(seconds=10)
    async with memdb() as s:
        await s.execute(sa_update(Alert).values(cleared_at=past))
        await s.commit()

    await ev._trigger(state, "high_altitude")

    async with memdb() as s:
        rows = (await s.execute(select(Alert).order_by(Alert.id))).scalars().all()

    assert len(rows) == 2, f"expected 2 rows (old cleared + new), got {len(rows)}"
    assert rows[0].cleared_at is not None
    assert rows[1].cleared_at is None


async def test_first_trigger_inserts_row(memdb):
    """With no prior row, trigger inserts a new one as before."""
    ev = AlertEvaluator()
    await ev.start()
    state = _mk("a70116", settings.alert_high_altitude_ft + 1000)

    await ev._trigger(state, "high_altitude")

    async with memdb() as s:
        rows = (await s.execute(select(Alert))).scalars().all()

    assert len(rows) == 1
    assert rows[0].cleared_at is None
