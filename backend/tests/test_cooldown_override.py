"""Tests for persistent cooldown overrides.

The CooldownTracker has two layers:
  1. In-memory TTL dict (existing behavior, see test_cooldown.py)
  2. Persistent overrides in the `cooldown_overrides` table (this file)

When an override is active for (hex, kind), `allow()` returns False regardless
of the TTL layer — so mutes survive a backend restart.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db import session as session_module
from app.db.models import Base, CooldownOverride
from app.notifications import cooldown as cooldown_module
from app.notifications.cooldown import CooldownTracker


@pytest_asyncio.fixture
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

    # Patch every path where session_scope is imported by name.
    monkeypatch.setattr(cooldown_module, "session_scope", fake_scope)
    monkeypatch.setattr(session_module, "session_scope", fake_scope)

    try:
        yield Session
    finally:
        await engine.dispose()


async def test_set_override_writes_row_and_cache(memdb):
    ct = CooldownTracker(ttl=timedelta(hours=6))
    until = datetime.now(UTC) + timedelta(hours=24)
    await ct.set_override("a12345", "watchlist", until_at=until, source="telegram_reply")

    # In-memory cache updated
    assert ("a12345", "watchlist") in ct._overrides

    # DB row persisted
    async with memdb() as s:
        rows = (await s.execute(select(CooldownOverride))).scalars().all()
    assert len(rows) == 1
    assert rows[0].hex == "a12345"
    assert rows[0].kind == "watchlist"
    assert rows[0].source == "telegram_reply"


async def test_allow_returns_false_when_override_active(memdb):
    ct = CooldownTracker(ttl=timedelta(hours=6))
    until = datetime.now(UTC) + timedelta(hours=24)
    await ct.set_override("a12345", "watchlist", until_at=until)

    # The TTL dict is empty — without the override this would return True (first
    # event). The override must be what's suppressing it.
    allowed = ct.allow("a12345", "watchlist", datetime.now(UTC))
    assert allowed is False


async def test_allow_resumes_prior_behavior_when_override_expired(memdb):
    ct = CooldownTracker(ttl=timedelta(hours=6))
    past = datetime.now(UTC) - timedelta(hours=1)
    await ct.set_override("a12345", "watchlist", until_at=past)

    # Even though an override exists, it expired in the past, so TTL logic
    # applies: first call returns True (no prior allow).
    allowed = ct.allow("a12345", "watchlist", datetime.now(UTC))
    assert allowed is True
    # The expired entry is cleaned from the in-memory cache lazily.
    assert ("a12345", "watchlist") not in ct._overrides


async def test_load_overrides_picks_up_existing_rows(memdb):
    # Seed rows directly to simulate pre-restart state
    future = datetime.now(UTC) + timedelta(hours=12)
    past = datetime.now(UTC) - timedelta(hours=1)
    now = datetime.now(UTC)
    async with memdb() as s:
        s.add_all(
            [
                CooldownOverride(
                    hex="a00001",
                    kind="watchlist",
                    until_at=future,
                    source="telegram_reply",
                    created_at=now,
                ),
                CooldownOverride(
                    hex="a00002",
                    kind="military",
                    until_at=past,  # expired — should NOT load
                    source="telegram_reply",
                    created_at=now,
                ),
            ]
        )
        await s.commit()

    ct = CooldownTracker(ttl=timedelta(hours=6))
    await ct.load_overrides()

    assert ("a00001", "watchlist") in ct._overrides
    # Expired rows are skipped on load
    assert ("a00002", "military") not in ct._overrides

    # And the active one suppresses allow()
    assert ct.allow("a00001", "watchlist", datetime.now(UTC)) is False


async def test_set_override_upserts_existing_row(memdb):
    ct = CooldownTracker(ttl=timedelta(hours=6))
    first = datetime.now(UTC) + timedelta(hours=6)
    second = datetime.now(UTC) + timedelta(hours=48)

    await ct.set_override("a12345", "watchlist", until_at=first)
    await ct.set_override("a12345", "watchlist", until_at=second, source="api")

    async with memdb() as s:
        rows = (await s.execute(select(CooldownOverride))).scalars().all()
    # Exactly one row due to the (hex, kind) uniqueness constraint
    assert len(rows) == 1
    # New until_at and source replaced the old
    assert rows[0].source == "api"
    # Compare ignoring microseconds + tz normalization
    persisted = rows[0].until_at
    if persisted.tzinfo is None:
        persisted = persisted.replace(tzinfo=UTC)
    assert abs((persisted - second).total_seconds()) < 1


async def test_emergency_bypass_ignores_override(memdb):
    """Bypass=True (emergencies) is absolute — overrides must not suppress it."""
    ct = CooldownTracker(ttl=timedelta(hours=6))
    until = datetime.now(UTC) + timedelta(hours=24)
    await ct.set_override("a12345", "emergency", until_at=until)

    assert ct.allow("a12345", "emergency", datetime.now(UTC), bypass=True) is True
