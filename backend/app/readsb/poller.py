"""1Hz poller — reads aircraft.json (HTTP or file), publishes deltas."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
import orjson

from app.config import settings
from app.events.bus import bus
from app.logging import get_logger
from app.readsb.parser import parse_snapshot
from app.readsb.schema import AircraftState
from app.readsb.state import AircraftRegistry

log = get_logger(__name__)


class ReadsbPoller:
    """Reads readsb's aircraft.json on an interval, publishes deltas."""

    def __init__(self, registry: AircraftRegistry | None = None) -> None:
        self.registry = registry or AircraftRegistry()
        self._task: asyncio.Task[None] | None = None
        self._stop_evt = asyncio.Event()
        self._http: httpx.AsyncClient | None = None
        self.last_tick: datetime | None = None
        self.last_error: str | None = None
        self.tick_count: int = 0
        self.on_delta_callbacks: list = []

    def register_delta_callback(self, cb) -> None:  # type: ignore[no-untyped-def]
        """Synchronous or async callback called on every tick with non-empty states."""
        self.on_delta_callbacks.append(cb)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_evt.clear()
        if settings.readsb_aircraft_url:
            self._http = httpx.AsyncClient(
                timeout=settings.http_timeout_s,
                headers={"User-Agent": "adsb-tracker/0.1"},
            )
        self._task = asyncio.create_task(self._run(), name="readsb-poller")
        log.info(
            "poller_started",
            interval=settings.poll_interval_s,
            source=settings.readsb_aircraft_url or str(settings.readsb_json_path),
        )

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None
        if self._http:
            await self._http.aclose()
            self._http = None
        log.info("poller_stopped")

    def current(self) -> list[AircraftState]:
        return self.registry.snapshot()

    async def _run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                await self._tick()
            except Exception as e:  # noqa: BLE001
                self.last_error = repr(e)
                log.exception("poller_tick_error")
            try:
                await asyncio.wait_for(self._stop_evt.wait(), timeout=settings.poll_interval_s)
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        raw = await self._read()
        if raw is None:
            return
        now = datetime.now(UTC)
        states = parse_snapshot(raw, now=now)
        delta = self.registry.apply(states)
        self.last_tick = now
        self.tick_count += 1

        # Fan out to subsystems — history writer, enrichment coordinator, alerts, stats
        if delta.has_changes or states:
            for cb in self.on_delta_callbacks:
                try:
                    result = cb(delta, states, now)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:  # noqa: BLE001
                    log.exception("poller_callback_error", callback=getattr(cb, "__qualname__", repr(cb)))

        if delta.has_changes:
            await bus.publish("aircraft.delta", delta.model_dump(mode="json"))

    async def _read(self) -> dict[str, Any] | None:
        url = settings.readsb_aircraft_url
        if url and self._http:
            return await self._read_http(url)
        return await self._read_file(settings.readsb_json_path)

    async def _read_http(self, url: str) -> dict[str, Any] | None:
        try:
            assert self._http is not None
            r = await self._http.get(url)
            if r.status_code != 200:
                log.warning("readsb_http_status", url=url, status=r.status_code)
                return None
            return orjson.loads(r.content)
        except (httpx.HTTPError, orjson.JSONDecodeError) as e:
            log.warning("readsb_http_failed", url=url, error=str(e))
            return None

    @staticmethod
    async def _read_file(path) -> dict[str, Any] | None:  # type: ignore[no-untyped-def]
        try:
            def _read() -> dict[str, Any]:
                with open(path, "rb") as f:
                    return orjson.loads(f.read())

            return await asyncio.to_thread(_read)
        except FileNotFoundError:
            log.warning("readsb_json_missing", path=str(path))
            return None
        except orjson.JSONDecodeError as e:
            log.warning("readsb_json_parse_error", error=str(e))
            return None
