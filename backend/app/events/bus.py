"""Simple in-process async pub/sub.

Publishers call `bus.publish(topic, data)`. Subscribers get a queue and read
from it. Slow subscribers drop on backpressure rather than blocking the
publisher — the dashboard is best-effort; missing a tick is better than
stalling the poller.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from app.logging import get_logger

log = get_logger(__name__)

_QUEUE_MAXSIZE = 256


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)

    def subscribe(self, topic: str) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        self._subs[topic].add(q)
        return q

    def unsubscribe(self, topic: str, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subs[topic].discard(q)

    async def publish(self, topic: str, data: dict[str, Any]) -> None:
        msg = {"type": topic, "data": data}
        for q in list(self._subs[topic]):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                log.warning("bus_backpressure_drop", topic=topic)

    @property
    def topics(self) -> list[str]:
        return list(self._subs.keys())


bus = EventBus()
