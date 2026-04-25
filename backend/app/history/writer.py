"""Batched position inserter. Flushes every N seconds."""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.db.models import Position
from app.db.session import session_scope
from app.logging import get_logger
from app.readsb.schema import AircraftDelta, AircraftState

log = get_logger(__name__)


class HistoryWriter:
    def __init__(self) -> None:
        self._buf: deque[dict[str, Any]] = deque()
        self._task: asyncio.Task[None] | None = None
        self._stop_evt = asyncio.Event()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_evt.clear()
        self._task = asyncio.create_task(self._flush_loop(), name="history-writer")
        log.info("history_writer_started", flush_interval=settings.position_flush_interval_s)

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None
        await self._flush()  # drain on shutdown
        log.info("history_writer_stopped")

    async def on_delta(
        self,
        delta: AircraftDelta,
        states: list[AircraftState],
        now: datetime,
    ) -> None:
        for state in states:
            if state.lat is None or state.lon is None:
                continue
            self._buf.append(
                {
                    "hex": state.hex,
                    "ts": now,
                    "lat": state.lat,
                    "lon": state.lon,
                    "alt_baro": state.alt_baro,
                    "gs": state.gs,
                    "track": state.track,
                    "baro_rate": state.baro_rate,
                    "rssi": state.rssi,
                }
            )

    async def _flush_loop(self) -> None:
        while not self._stop_evt.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_evt.wait(), timeout=settings.position_flush_interval_s
                )
            except asyncio.TimeoutError:
                pass
            await self._flush()

    async def _flush(self) -> None:
        if not self._buf:
            return
        async with self._lock:
            rows = list(self._buf)
            self._buf.clear()
        try:
            async with session_scope() as s:
                await s.run_sync(
                    lambda sync_s: sync_s.bulk_insert_mappings(Position, rows)
                )
            log.debug("positions_flushed", count=len(rows))
        except Exception:  # noqa: BLE001
            log.exception("history_flush_failed", count=len(rows))


writer = HistoryWriter()
