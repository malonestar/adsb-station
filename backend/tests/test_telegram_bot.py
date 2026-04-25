"""Tests for the interactive Telegram bot command router + reply handler.

We stub session_scope to an in-memory SQLite engine, stub the watchlist refresh
(it touches the real session factory in app.alerts.watchlist), and never hit the
real Telegram API.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.alerts import watchlist as watchlist_module
from app.db import session as session_module
from app.db.models import Alert, Base, TelegramMessageMap, Watchlist
from app.notifications import cooldown as cooldown_module
from app.notifications import dispatcher as dispatcher_module
from app.notifications.cooldown import CooldownTracker
from app.readsb.schema import AircraftState
from app.telegram_bot import handlers as handlers_module
from app.telegram_bot.handlers import CommandRouter


# ─────────────────────────────────────────────────────────────────────────
# In-memory DB fixture
# ─────────────────────────────────────────────────────────────────────────


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

    # Patch everywhere session_scope is imported by name.
    monkeypatch.setattr(handlers_module, "session_scope", fake_scope)
    monkeypatch.setattr(watchlist_module, "session_scope", fake_scope)
    monkeypatch.setattr(session_module, "session_scope", fake_scope)
    monkeypatch.setattr(cooldown_module, "session_scope", fake_scope)

    # Watchlist.refresh() uses session_scope too — rebind its in-memory map fresh.
    async def do_refresh() -> None:
        async with fake_scope() as s:
            rows = (await s.execute(select(Watchlist))).scalars().all()
            new_map: dict[str, dict[str, Watchlist]] = {}
            for r in rows:
                new_map.setdefault(r.kind, {})[r.value.lower()] = r
            watchlist_module.watchlist._by_kind = new_map

    monkeypatch.setattr(watchlist_module.watchlist, "refresh", do_refresh)

    try:
        yield Session
    finally:
        await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────
# Fake poller
# ─────────────────────────────────────────────────────────────────────────


class FakePoller:
    """Stands in for ReadsbPoller; only needs .current()."""

    def __init__(self, states: list[AircraftState] | None = None) -> None:
        self._states = states or []
        self.tick_count = 1
        self.last_tick = datetime.now(UTC)

    def current(self) -> list[AircraftState]:
        return list(self._states)


def _mk_state(**kwargs) -> AircraftState:
    base = dict(
        hex="a12345",
        flight="UAL123",
        updated_at=datetime.now(UTC),
    )
    base.update(kwargs)
    return AircraftState(**base)


# ─────────────────────────────────────────────────────────────────────────
# /status
# ─────────────────────────────────────────────────────────────────────────


async def test_status_returns_formatted_text(memdb):
    poller = FakePoller(
        [
            _mk_state(hex="a11111", lat=39.7, lon=-105.0, alt_baro=30000),
            _mk_state(hex="a22222"),
        ]
    )
    router = CommandRouter(poller=poller)
    out = await router.handle_command("/status", chat_id=1)
    assert out is not None
    assert "STATION STATUS" in out
    assert "Aircraft:" in out
    assert "Msgs/sec:" in out


async def test_status_without_poller_reports_unavailable(memdb):
    router = CommandRouter(poller=None)
    out = await router.handle_command("/status", chat_id=1)
    assert out is not None
    assert "unavailable" in out.lower()


# ─────────────────────────────────────────────────────────────────────────
# /watch + /unwatch
# ─────────────────────────────────────────────────────────────────────────


async def test_watch_adds_to_watchlist(memdb):
    router = CommandRouter()
    out = await router.handle_command("/watch a1b2c3 Elon", chat_id=1)
    assert out is not None
    assert "a1b2c3" in out
    assert "watchlist" in out.lower()
    async with memdb() as s:
        rows = (await s.execute(select(Watchlist))).scalars().all()
    assert len(rows) == 1
    assert rows[0].value == "a1b2c3"
    assert rows[0].label == "Elon"


async def test_watch_is_idempotent(memdb):
    router = CommandRouter()
    await router.handle_command("/watch a1b2c3 First", chat_id=1)
    out = await router.handle_command("/watch a1b2c3 Second", chat_id=1)
    assert out is not None
    assert "already" in out.lower()
    async with memdb() as s:
        rows = (await s.execute(select(Watchlist))).scalars().all()
    assert len(rows) == 1


async def test_watch_rejects_bad_hex(memdb):
    router = CommandRouter()
    out = await router.handle_command("/watch not-a-hex", chat_id=1)
    assert out is not None
    assert "hex" in out.lower()


async def test_unwatch_removes(memdb):
    router = CommandRouter()
    await router.handle_command("/watch a1b2c3", chat_id=1)
    out = await router.handle_command("/unwatch a1b2c3", chat_id=1)
    assert out is not None
    assert "removed" in out.lower()
    async with memdb() as s:
        rows = (await s.execute(select(Watchlist))).scalars().all()
    assert len(rows) == 0


async def test_unwatch_missing_is_polite(memdb):
    router = CommandRouter()
    out = await router.handle_command("/unwatch a1b2c3", chat_id=1)
    assert out is not None
    assert "wasn't" in out.lower()


# ─────────────────────────────────────────────────────────────────────────
# /last
# ─────────────────────────────────────────────────────────────────────────


async def test_last_empty(memdb):
    router = CommandRouter()
    out = await router.handle_command("/last", chat_id=1)
    assert out is not None
    assert "no alerts" in out.lower()


async def test_last_with_rows(memdb):
    now = datetime.now(UTC)
    async with memdb() as s:
        s.add(
            Alert(
                hex="a70116",
                kind="high_altitude",
                triggered_at=now - timedelta(hours=1),
                payload={"flight": "UAL1234"},
            )
        )
        s.add(
            Alert(
                hex="a22753",
                kind="high_altitude",
                triggered_at=now - timedelta(minutes=5),
                payload={"flight": "N238MH"},
            )
        )
        await s.commit()
    router = CommandRouter()
    out = await router.handle_command("/last", chat_id=1)
    assert out is not None
    assert "a70116" in out
    assert "a22753" in out
    assert "high_altitude" in out


# ─────────────────────────────────────────────────────────────────────────
# /help
# ─────────────────────────────────────────────────────────────────────────


async def test_help_text_listed(memdb):
    router = CommandRouter()
    out = await router.handle_command("/help", chat_id=1)
    assert out is not None
    assert "/status" in out
    assert "/nearest" in out
    assert "/watch" in out


async def test_unknown_command(memdb):
    router = CommandRouter()
    out = await router.handle_command("/bogus", chat_id=1)
    assert out is not None
    assert "unknown" in out.lower()


# ─────────────────────────────────────────────────────────────────────────
# Reply handling
# ─────────────────────────────────────────────────────────────────────────


async def test_reply_watch_adds_hex_from_message_map(memdb):
    # Seed a map entry: alert message_id 111 → hex a99999
    async with memdb() as s:
        s.add(
            TelegramMessageMap(
                chat_id=1234567890,
                message_id=111,
                hex="a99999",
                callsign="N99ZZ",
                kind="watchlist",
                sent_at=datetime.now(UTC),
            )
        )
        await s.commit()
    router = CommandRouter()
    out = await router.handle_reply(
        original_message_id=111, chat_id=1234567890, reply_text="watch"
    )
    assert out is not None
    assert "a99999" in out
    async with memdb() as s:
        rows = (await s.execute(select(Watchlist))).scalars().all()
    assert any(r.value == "a99999" for r in rows)


async def test_reply_unknown_falls_back_to_help(memdb):
    async with memdb() as s:
        s.add(
            TelegramMessageMap(
                chat_id=1,
                message_id=222,
                hex="a88888",
                callsign=None,
                kind="watchlist",
                sent_at=datetime.now(UTC),
            )
        )
        await s.commit()
    router = CommandRouter()
    out = await router.handle_reply(
        original_message_id=222, chat_id=1, reply_text="blerg"
    )
    assert out is not None
    assert "didn't understand" in out.lower() or "help" in out.lower()


async def test_reply_to_unmapped_message(memdb):
    router = CommandRouter()
    out = await router.handle_reply(
        original_message_id=999999, chat_id=1, reply_text="watch"
    )
    assert out is not None
    assert "mapping" in out.lower() or "watch" in out.lower()


async def test_reply_mute_seeds_cooldown(memdb, monkeypatch):
    # Replace the dispatcher's cooldown tracker with a fresh one we can inspect
    fresh = CooldownTracker(ttl=timedelta(hours=6))
    monkeypatch.setattr(dispatcher_module.dispatcher, "_cooldown", fresh)
    async with memdb() as s:
        s.add(
            TelegramMessageMap(
                chat_id=1,
                message_id=333,
                hex="a77777",
                callsign=None,
                kind="watchlist",
                sent_at=datetime.now(UTC),
            )
        )
        await s.commit()
    router = CommandRouter()
    out = await router.handle_reply(
        original_message_id=333, chat_id=1, reply_text="mute"
    )
    assert out is not None
    assert "mute" in out.lower()
    # The tracker should now refuse to allow this (hex, kind) because we
    # seeded a future timestamp.
    allowed = fresh.allow(
        "a77777", "watchlist", datetime.now(UTC)
    )
    assert allowed is False
