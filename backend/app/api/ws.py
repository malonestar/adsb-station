"""WebSocket hub — multiplexed channel, auto-fan-out from EventBus."""

from __future__ import annotations

import asyncio

import orjson
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.events.bus import bus
from app.logging import get_logger

log = get_logger(__name__)

router = APIRouter()

_TOPICS = [
    "aircraft.delta",
    "aircraft.enriched",
    "alert.new",
    "alert.cleared",
    "stats.tick",
    "feed.status",
]


@router.websocket("/ws")
async def ws(ws: WebSocket) -> None:
    await ws.accept()
    queues = {t: bus.subscribe(t) for t in _TOPICS}
    log.info("ws_client_connected")

    async def pump(topic: str, q) -> None:  # type: ignore[no-untyped-def]
        while True:
            msg = await q.get()
            try:
                # Send as text — frontend does JSON.parse(String(ev.data))
                await ws.send_text(orjson.dumps(msg).decode("utf-8"))
            except Exception:  # noqa: BLE001
                return

    tasks = [asyncio.create_task(pump(t, q), name=f"ws-pump-{t}") for t, q in queues.items()]
    try:
        while True:
            # Handle pings/keepalive frames; clients can also request specific data
            raw = await ws.receive_text()
            if raw == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("ws_error")
    finally:
        for t in tasks:
            t.cancel()
        for topic, q in queues.items():
            bus.unsubscribe(topic, q)
        log.info("ws_client_disconnected")
