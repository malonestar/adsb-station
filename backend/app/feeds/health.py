"""Per-feeder health — reads Docker socket, probes readsb stats."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from app.config import settings
from app.db.models import FeedStatus
from app.db.session import session_scope
from app.events.bus import bus
from app.logging import get_logger

log = get_logger(__name__)

# Known feeder container names. The four open-data aggregators (adsb.lol,
# adsb.fi, airplanes.live, adsbexchange) feed via ultrafeeder's built-in
# ULTRAFEEDER_CONFIG rather than separate containers, so they're tracked
# implicitly through the ultrafeeder entry.
KNOWN_FEEDERS = [
    "ultrafeeder",
    "adsb-backend",
    "piaware",
    "fr24feed",
    "rbfeeder",
    "opensky-feeder",
]


class FeedsHealth:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._stop_evt = asyncio.Event()
        self._last_status: dict[str, dict[str, Any]] = {}

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_evt.clear()
        self._task = asyncio.create_task(self._run(), name="feeds-health")
        log.info("feeds_health_started")

    async def stop(self) -> None:
        self._stop_evt.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None

    def current(self) -> list[dict[str, Any]]:
        return list(self._last_status.values())

    async def _run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                await self._tick()
            except Exception:  # noqa: BLE001
                log.exception("feeds_health_tick_error")
            try:
                await asyncio.wait_for(self._stop_evt.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        statuses = await asyncio.to_thread(self._inspect_containers)
        # Ultrafeeder's /data/stats.json isn't exposed by default in this image,
        # so we no longer probe it here. Message rate is derived by the live
        # stats subsystem directly from the aircraft snapshot, which is more
        # accurate anyway.

        now = datetime.now(UTC)
        for s in statuses:
            s["updated_at"] = now.isoformat()
            self._last_status[s["name"]] = s
            await self._persist(s, now)

        await bus.publish("feed.status", {"feeds": statuses})

    @staticmethod
    def _inspect_containers() -> list[dict[str, Any]]:
        """Sync Docker SDK call — runs in a thread."""
        try:
            import docker  # type: ignore

            client = docker.DockerClient(base_url=f"unix://{settings.docker_socket}")
            containers = {c.name: c for c in client.containers.list(all=True)}
        except Exception as e:  # noqa: BLE001
            log.warning("docker_inspect_failed", error=str(e))
            return [
                {"name": name, "state": "unknown", "last_error": str(e)}
                for name in KNOWN_FEEDERS
            ]

        out: list[dict[str, Any]] = []
        for name in KNOWN_FEEDERS:
            c = containers.get(name)
            if c is None:
                out.append({"name": name, "state": "absent", "last_error": None})
                continue
            state = c.attrs.get("State", {})
            health = (state.get("Health") or {}).get("Status") or state.get("Status", "unknown")
            # readsb/ultrafeeder health states: healthy/unhealthy/starting, or running without healthcheck
            if health == "healthy":
                s = "ok"
            elif health == "starting":
                s = "warn"
            elif health in ("running",) and not state.get("Health"):
                s = "ok"
            elif health == "unhealthy" or state.get("Status") == "exited":
                s = "down"
            else:
                s = "warn"
            out.append(
                {
                    "name": name,
                    "state": s,
                    "docker_status": state.get("Status"),
                    "docker_health": health,
                    "started_at": state.get("StartedAt"),
                    "last_error": None,
                }
            )
        return out

    async def _persist(self, s: dict[str, Any], now: datetime) -> None:
        async with session_scope() as sess:
            row = await sess.get(FeedStatus, s["name"])
            if row is None:
                sess.add(
                    FeedStatus(
                        feeder_name=s["name"],
                        state=s["state"],
                        last_ok_at=now if s["state"] == "ok" else None,
                        last_error=s.get("last_error"),
                        updated_at=now,
                    )
                )
            else:
                row.state = s["state"]
                if s["state"] == "ok":
                    row.last_ok_at = now
                row.last_error = s.get("last_error")
                row.updated_at = now


health = FeedsHealth()
