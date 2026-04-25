"""Tests for the watchlist notify flag and alert-gating behavior."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.alerts import rules as rules_module
from app.alerts import watchlist as wl_module
from app.alerts.rules import AlertEvaluator
from app.alerts.watchlist import WatchlistStore
from app.db.models import Base, Watchlist as WatchlistRow
from app.events.bus import bus
from app.readsb.schema import AircraftState


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

    monkeypatch.setattr(rules_module, "session_scope", fake_scope)
    monkeypatch.setattr(wl_module, "session_scope", fake_scope)

    async def noop_publish(*args, **kwargs):
        return None

    monkeypatch.setattr(bus, "publish", noop_publish)
    try:
        yield Session
    finally:
        await engine.dispose()


# ── WatchlistStore.add notify defaults ──────────────────────────────────


async def test_add_hex_defaults_to_notify_true(memdb):
    store = WatchlistStore()
    row = await store.add(kind="hex", value="abc123")
    assert row.notify is True


@pytest.mark.parametrize("kind", ["reg", "type", "operator"])
async def test_add_high_volume_kinds_default_to_notify_false(memdb, kind):
    store = WatchlistStore()
    row = await store.add(kind=kind, value="EXAMPLE")
    assert row.notify is False, f"{kind} should default to passive"


async def test_add_explicit_notify_overrides_default(memdb):
    store = WatchlistStore()
    row = await store.add(kind="operator", value="NASA", notify=True)
    assert row.notify is True


# ── WatchlistStore.set_notify toggles in place ──────────────────────────


async def test_set_notify_flips_existing_entry(memdb):
    store = WatchlistStore()
    row = await store.add(kind="type", value="C172")
    assert row.notify is False
    updated = await store.set_notify(row.id, True)
    assert updated is not None
    assert updated.notify is True
    # set_notify also refreshes the in-memory cache
    cached = store.match("type", "C172")
    assert cached is not None
    assert cached.notify is True


async def test_set_notify_returns_none_for_missing_entry(memdb):
    store = WatchlistStore()
    result = await store.set_notify(9999, True)
    assert result is None


# ── AlertEvaluator gates on notify ──────────────────────────────────────


def _state(hex_code: str, **kwargs) -> AircraftState:
    return AircraftState(hex=hex_code, updated_at=datetime.now(UTC), **kwargs)


async def test_passive_watchlist_match_does_not_emit_alert(memdb, monkeypatch):
    """type=B738 with notify=False — matches but generates no 'watchlist' kind."""
    # Use the module-level singleton so AlertEvaluator's import resolves correctly.
    await wl_module.watchlist.refresh()  # clear residual state
    await wl_module.watchlist.add(kind="type", value="B738", notify=False)

    ev = AlertEvaluator()
    state = _state("aaaa01", type_code="B738")
    kinds = ev._evaluate(state)
    assert "watchlist" not in kinds


async def test_active_watchlist_match_emits_alert(memdb):
    """hex entry with notify=True — emits 'watchlist'."""
    await wl_module.watchlist.refresh()
    await wl_module.watchlist.add(kind="hex", value="bbbb02", notify=True)

    ev = AlertEvaluator()
    state = _state("bbbb02", type_code="C172")
    kinds = ev._evaluate(state)
    assert "watchlist" in kinds


async def test_explicitly_active_high_volume_match_emits_alert(memdb):
    """type=C172 explicitly opted into notify=True still emits 'watchlist'."""
    await wl_module.watchlist.refresh()
    await wl_module.watchlist.add(kind="type", value="C172", notify=True)

    ev = AlertEvaluator()
    state = _state("cccc03", type_code="C172")
    kinds = ev._evaluate(state)
    assert "watchlist" in kinds
