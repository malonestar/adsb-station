"""Watchlist CRUD + in-memory cache for fast match lookups."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.db.models import Watchlist as WatchlistRow
from app.db.session import session_scope
from app.logging import get_logger

log = get_logger(__name__)


class WatchlistStore:
    """Cached lookup of watchlist entries by kind/value."""

    def __init__(self) -> None:
        self._by_kind: dict[str, dict[str, WatchlistRow]] = {}
        self._lock = asyncio.Lock()

    async def refresh(self) -> None:
        async with self._lock:
            async with session_scope() as s:
                rows = (await s.execute(select(WatchlistRow))).scalars().all()
                new_map: dict[str, dict[str, WatchlistRow]] = {}
                for r in rows:
                    new_map.setdefault(r.kind, {})[r.value.lower()] = r
                self._by_kind = new_map

    async def all(self) -> list[WatchlistRow]:
        async with session_scope() as s:
            return list((await s.execute(select(WatchlistRow))).scalars().all())

    async def add(self, kind: str, value: str, label: str | None = None) -> WatchlistRow:
        kind = kind.lower()
        if kind not in {"hex", "reg", "type", "operator"}:
            raise ValueError(f"unknown watchlist kind: {kind}")
        async with session_scope() as s:
            row = WatchlistRow(
                kind=kind,
                value=value,
                label=label,
                created_at=datetime.now(UTC),
            )
            s.add(row)
            await s.flush()
            await s.refresh(row)
        await self.refresh()
        return row

    async def remove(self, entry_id: int) -> bool:
        async with session_scope() as s:
            r = await s.execute(delete(WatchlistRow).where(WatchlistRow.id == entry_id))
            deleted = r.rowcount or 0
        if deleted:
            await self.refresh()
        return bool(deleted)

    def match(self, kind: str, value: str | None) -> WatchlistRow | None:
        if not value:
            return None
        return self._by_kind.get(kind, {}).get(value.lower())


watchlist = WatchlistStore()
