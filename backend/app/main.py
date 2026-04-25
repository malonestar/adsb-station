"""FastAPI entrypoint with full lifespan wiring."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.alerts.rules import evaluator as alert_evaluator
from app.alerts.seed import seed_watchlist_if_empty
from app.notifications.dispatcher import dispatcher as notification_dispatcher
from app.api.rest import router as rest_router
from app.api.ws import router as ws_router
from app.config import settings
from app.db.session import enable_wal
from app.enrichment.coordinator import coordinator as enrichment_coordinator
from app.feeds.health import health as feeds_health
from app.history.writer import writer as history_writer
from app.logging import configure_logging, get_logger
from app.readsb.poller import ReadsbPoller
from app.stats.aggregates import configure_jobs, scheduler
from app.stats.live import live_stats
from app.telegram_bot.poller import TelegramBot

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(level=settings.log_level, json=settings.log_json)
    log.info(
        "backend_startup",
        station=settings.feeder_name,
        lat=settings.feeder_lat,
        lon=settings.feeder_lon,
        db_path=str(settings.db_path),
        readsb_path=str(settings.readsb_json_path),
    )

    await enable_wal()

    poller = ReadsbPoller()
    app.state.poller = poller

    # Start subsystems (order matters — dependencies first)
    await history_writer.start()
    await enrichment_coordinator.start()
    await seed_watchlist_if_empty()
    await alert_evaluator.start()
    await notification_dispatcher.start()
    await feeds_health.start()

    # Register poller callbacks so every tick fans out to subsystems
    poller.register_delta_callback(history_writer.on_delta)
    poller.register_delta_callback(enrichment_coordinator.on_delta)
    poller.register_delta_callback(alert_evaluator.on_delta)
    poller.register_delta_callback(live_stats.on_delta)

    configure_jobs()
    scheduler.start()
    await poller.start()

    # ─── Interactive Telegram bot (long-polling) ─────────────────────────
    # Reuses the same bot token + chat_id as the outbound alerts. If either
    # is missing we skip it cleanly so the backend still comes up.
    bot: TelegramBot | None = None
    bot_task: asyncio.Task[None] | None = None
    if settings.telegram_bot_token and settings.telegram_chat_id:
        try:
            chat_id_int = int(settings.telegram_chat_id)
            bot = TelegramBot(
                settings.telegram_bot_token,
                chat_id_int,
                poller=poller,
            )
            bot_task = asyncio.create_task(bot.run(), name="telegram-bot")
            log.info("telegram_bot_started", chat_id=chat_id_int)
        except (TypeError, ValueError) as e:
            log.warning(
                "telegram_bot_chat_id_invalid",
                chat_id=settings.telegram_chat_id,
                error=str(e),
            )
    else:
        log.warning(
            "telegram_bot_disabled",
            reason="ADSB_TELEGRAM_BOT_TOKEN or ADSB_TELEGRAM_CHAT_ID missing",
        )

    try:
        yield
    finally:
        log.info("backend_shutdown")
        if bot is not None and bot_task is not None:
            await bot.stop()
            try:
                await asyncio.wait_for(bot_task, timeout=5)
            except asyncio.TimeoutError:
                bot_task.cancel()
                try:
                    await bot_task
                except (asyncio.CancelledError, Exception):  # noqa: BLE001
                    pass
        await poller.stop()
        await feeds_health.stop()
        await notification_dispatcher.stop()
        await alert_evaluator.stop()
        await enrichment_coordinator.stop()
        await history_writer.stop()
        try:
            scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass


app = FastAPI(
    title="ADS-B Backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, object]:
    poller = getattr(app.state, "poller", None)
    ready = poller is not None and poller.tick_count > 0
    return {"ready": ready, "tick_count": poller.tick_count if poller else 0}


app.include_router(rest_router)
app.include_router(ws_router)
