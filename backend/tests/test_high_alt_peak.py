"""Tests for high_altitude peak tracking + climb-renotify (Issue 2 A+B+C).

Regression: alert payload showed trigger-time altitude (e.g. 45,025) for an
aircraft that climbed to 60,000. Fix tracks peak alt during the active alert
and re-fires notification when the aircraft climbs by ≥10,000 ft above the
last-notified altitude.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.alerts import rules as rules_module
from app.alerts.rules import AlertEvaluator
from app.config import settings
from app.db.models import Alert, Base
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

    async def noop_refresh():
        return None

    monkeypatch.setattr(rules_module.watchlist, "refresh", noop_refresh)
    try:
        yield Session
    finally:
        await engine.dispose()


@pytest.fixture
def collected_events(monkeypatch):
    """Capture all events published via bus.publish during the test."""
    events: list[tuple[str, dict]] = []

    async def fake_publish(topic, data):
        events.append((topic, data))

    monkeypatch.setattr(bus, "publish", fake_publish)
    return events


def _state(hex_code: str, alt: int) -> AircraftState:
    return AircraftState(hex=hex_code, alt_baro=alt, updated_at=datetime.now(UTC))


async def test_peak_alt_grows_with_climb(memdb, collected_events):
    """Peak alt in the alert payload grows as the aircraft climbs."""
    ev = AlertEvaluator()
    await ev.start()

    # Trigger at threshold + 25
    threshold = settings.alert_high_altitude_ft
    await ev._trigger(_state("aaa001", threshold + 25), "high_altitude")
    # Two more ticks at higher alt — must update peak in DB
    await ev._maybe_update_peak_alt(_state("aaa001", threshold + 5_000), ("aaa001", "high_altitude"))
    await ev._maybe_update_peak_alt(_state("aaa001", threshold + 15_000), ("aaa001", "high_altitude"))

    async with memdb() as s:
        row = (await s.execute(select(Alert))).scalar_one()
    assert row.payload["peak_alt_ft"] == threshold + 15_000


async def test_peak_alt_does_not_decrease(memdb, collected_events):
    """Tick at lower alt must not regress the peak."""
    ev = AlertEvaluator()
    await ev.start()
    threshold = settings.alert_high_altitude_ft
    await ev._trigger(_state("aaa002", threshold + 1_000), "high_altitude")
    # Climb to 55k
    await ev._maybe_update_peak_alt(_state("aaa002", threshold + 10_000), ("aaa002", "high_altitude"))
    # Then drop to 50k (level off / descend) — peak must stay at 55k
    await ev._maybe_update_peak_alt(_state("aaa002", threshold + 5_000), ("aaa002", "high_altitude"))

    async with memdb() as s:
        row = (await s.execute(select(Alert))).scalar_one()
    assert row.payload["peak_alt_ft"] == threshold + 10_000


async def test_renotify_fires_on_significant_climb(memdb, collected_events):
    """Climb ≥10,000 ft above last-notified must publish alert.renotify."""
    ev = AlertEvaluator()
    await ev.start()
    threshold = settings.alert_high_altitude_ft
    # Trigger at 45,025 (default threshold + 25)
    await ev._trigger(_state("aaa003", threshold + 25), "high_altitude")
    # Small climb (5k) — no renotify
    await ev._maybe_update_peak_alt(_state("aaa003", threshold + 5_000), ("aaa003", "high_altitude"))
    # Big climb (15k above last_notified) — must renotify
    await ev._maybe_update_peak_alt(_state("aaa003", threshold + 15_000), ("aaa003", "high_altitude"))

    renotify = [d for (t, d) in collected_events if t == "alert.renotify"]
    assert len(renotify) == 1
    p = renotify[0]["payload"]
    assert p["renotify"] is True
    assert p["alt_baro"] == threshold + 15_000
    assert p["previous_alt_ft"] == threshold + 25


async def test_renotify_throttled_to_climb_threshold(memdb, collected_events):
    """Multiple small climbs must not produce multiple renotifies."""
    ev = AlertEvaluator()
    await ev.start()
    threshold = settings.alert_high_altitude_ft
    await ev._trigger(_state("aaa004", threshold + 25), "high_altitude")
    # 4 small climbs of 3k each (total 12k) — only one cumulative climb fires renotify
    for delta in (3_000, 6_000, 9_000, 12_000):
        await ev._maybe_update_peak_alt(
            _state("aaa004", threshold + delta), ("aaa004", "high_altitude")
        )

    renotify = [d for (t, d) in collected_events if t == "alert.renotify"]
    # Only one renotify — at the +12k climb (first one above the 10k threshold)
    assert len(renotify) == 1
    assert renotify[0]["payload"]["alt_baro"] == threshold + 12_000


async def test_startup_seeds_peak_from_existing_alert(memdb, collected_events):
    """Restart-loaded uncleared alerts must seed peak/last-notified from payload.

    Otherwise the first post-restart tick compares alt against 0 and trips the
    +10k climb threshold, sending a phantom 'climbing' notification.
    """
    threshold = settings.alert_high_altitude_ft
    # Pre-populate DB with an uncleared high_altitude alert from a prior run.
    async with memdb() as s:
        s.add(
            Alert(
                hex="aaa006",
                kind="high_altitude",
                triggered_at=datetime.now(UTC),
                payload={"alt_baro": threshold + 1_000, "peak_alt_ft": threshold + 8_000},
            )
        )
        await s.commit()

    ev = AlertEvaluator()
    await ev.start()

    # First post-restart tick at the same alt as the persisted peak — must
    # NOT renotify, must NOT decrease peak.
    await ev._maybe_update_peak_alt(
        _state("aaa006", threshold + 8_000), ("aaa006", "high_altitude")
    )
    renotify = [d for (t, d) in collected_events if t == "alert.renotify"]
    assert len(renotify) == 0, "Phantom renotify on startup-loaded alert"
    assert ev._peak_alt[("aaa006", "high_altitude")] == threshold + 8_000


async def test_clear_resets_peak_state(memdb, collected_events):
    """When alert clears, peak/last-notified state must be wiped."""
    ev = AlertEvaluator()
    await ev.start()
    threshold = settings.alert_high_altitude_ft
    await ev._trigger(_state("aaa005", threshold + 25), "high_altitude")
    assert ("aaa005", "high_altitude") in ev._peak_alt
    assert ("aaa005", "high_altitude") in ev._last_notified_alt
    await ev._clear("aaa005", "high_altitude")
    assert ("aaa005", "high_altitude") not in ev._peak_alt
    assert ("aaa005", "high_altitude") not in ev._last_notified_alt
