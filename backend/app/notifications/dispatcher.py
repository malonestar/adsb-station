"""Dispatcher subscribes to alert.new on the bus and fans out to channel adapters.

Cooldown + enrichment happen here; individual channel adapters are stateless.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.db.models import AircraftCatalog, Watchlist
from app.db.session import session_scope
from app.events.bus import bus
from app.logging import get_logger
from app.notifications.cooldown import CooldownTracker
from app.notifications.discord import DiscordNotifier
from app.notifications.email import EmailNotifier
from app.notifications.formatter import FormattedMessage, format_message
from app.notifications.telegram import TelegramNotifier

log = get_logger(__name__)


class NotificationDispatcher:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._cooldown = CooldownTracker(
            ttl=timedelta(hours=settings.alert_cooldown_hours)
        )
        self._telegram = TelegramNotifier.maybe_create(
            settings.telegram_bot_token, settings.telegram_chat_id
        )
        self._discord = DiscordNotifier.maybe_create(settings.discord_webhook_url)
        self._email = EmailNotifier.maybe_create(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_password,
            settings.smtp_from,
            settings.smtp_to,
        )

    async def start(self) -> None:
        if self._task is not None:
            return
        # Rehydrate any persistent cooldown overrides (/mute from bot replies)
        # before we start processing alerts, so a mute set pre-restart still
        # suppresses after the restart.
        await self._cooldown.load_overrides()
        enabled = [
            n.name
            for n in (self._telegram, self._discord, self._email)
            if n is not None
        ]
        log.info(
            "dispatcher_starting",
            channels=enabled,
            cooldown_hours=settings.alert_cooldown_hours,
        )
        self._task = asyncio.create_task(self._run(), name="notification-dispatcher")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        new_q = bus.subscribe("alert.new")
        renotify_q = bus.subscribe("alert.renotify")
        try:
            await asyncio.gather(
                self._consume_loop(new_q, bypass_cooldown=False),
                # Re-notify events bypass cooldown — they only fire when the
                # rule itself decides re-notification is warranted (e.g.,
                # +10k climb on high_altitude). Cooldown was already enforced
                # at the original alert.new event.
                self._consume_loop(renotify_q, bypass_cooldown=True),
            )
        except asyncio.CancelledError:
            bus.unsubscribe("alert.new", new_q)
            bus.unsubscribe("alert.renotify", renotify_q)
            raise

    async def _consume_loop(
        self, q: asyncio.Queue[dict[str, Any]], *, bypass_cooldown: bool
    ) -> None:
        while True:
            event = await q.get()
            try:
                await self._handle(event["data"], bypass_cooldown=bypass_cooldown)
            except Exception:  # noqa: BLE001
                log.exception("dispatcher_handle_failed")

    async def _handle(self, alert: dict[str, Any], *, bypass_cooldown: bool = False) -> None:
        hex_code = alert.get("hex", "")
        kind = alert.get("kind", "")
        now = datetime.now(UTC)

        is_emergency = kind == "emergency"
        if not self._cooldown.allow(
            hex_code, kind, now, bypass=is_emergency or bypass_cooldown
        ):
            log.info("dispatcher_cooldown_suppressed", hex=hex_code, kind=kind)
            return

        enrichment = await self._fetch_enrichment(hex_code)
        msg = format_message(
            alert,
            enrichment=enrichment,
            dashboard_url=settings.dashboard_base_url,
        )
        await self._fanout(msg, kind=kind, alert=alert)

    async def _fetch_enrichment(self, hex_code: str) -> dict[str, Any]:
        """Pull cached photo / operator / watchlist label. All optional."""
        out: dict[str, Any] = {}
        async with session_scope() as s:
            cat = (
                await s.execute(
                    select(AircraftCatalog).where(AircraftCatalog.hex == hex_code)
                )
            ).scalar_one_or_none()
            if cat is not None:
                out["photo_url"] = cat.photo_url
                out["operator"] = cat.operator
            wl = (
                await s.execute(
                    select(Watchlist).where(
                        Watchlist.kind == "hex", Watchlist.value == hex_code
                    )
                )
            ).scalar_one_or_none()
            if wl is not None:
                out["watchlist_label"] = wl.label
        return out

    async def _fanout(
        self,
        msg: FormattedMessage,
        *,
        kind: str,
        alert: dict[str, Any] | None = None,
    ) -> None:
        coros = []
        if self._telegram:
            # Pass the alert through so the telegram notifier can persist a
            # (chat_id, message_id) → (hex, kind, callsign) mapping for replies.
            coros.append(
                self._safe_call(
                    self._telegram.name, self._telegram.notify(msg, alert=alert)
                )
            )
        if self._discord:
            coros.append(self._safe_call(self._discord.name, self._discord.notify(msg)))
        if self._email:
            coros.append(
                self._safe_call(self._email.name, self._email.notify(msg, kind=kind))
            )
        if not coros:
            log.info("dispatcher_no_channels_configured")
            return
        await asyncio.gather(*coros, return_exceptions=True)

    async def _safe_call(self, channel: str, coro: Any) -> None:
        try:
            await coro
        except Exception as e:  # noqa: BLE001
            log.warning("channel_send_failed", channel=channel, error=str(e))

    async def test_send(self, *, channel: str = "all") -> dict[str, str]:
        """Synthetic alert → selected channel(s). Used by POST /api/alerts/test."""
        fake_alert = {
            "hex": "ffffff",
            "kind": "watchlist",
            "triggered_at": datetime.now(UTC).isoformat(),
            "payload": {
                "flight": "TEST1234",
                "registration": "N-TEST",
                "type_code": "C17",
                "squawk": "1234",
                "emergency": None,
                "alt_baro": 35000,
                "distance_nm": 42.0,
                "lat": settings.feeder_lat,
                "lon": settings.feeder_lon,
            },
        }
        enrichment = {
            "operator": "Notification Test",
            "photo_url": None,
            "watchlist_label": "TEST: Alert Plumbing",
        }
        msg = format_message(
            fake_alert,
            enrichment=enrichment,
            dashboard_url=settings.dashboard_base_url,
        )
        results: dict[str, str] = {}
        targets = {
            "telegram": self._telegram,
            "discord": self._discord,
            "email": self._email,
        }
        for name, notifier in targets.items():
            if channel not in ("all", name):
                continue
            if notifier is None:
                results[name] = "disabled (missing env vars)"
                continue
            try:
                if name == "email":
                    await notifier.notify(msg, kind="watchlist")
                else:
                    await notifier.notify(msg)
                results[name] = "ok"
            except Exception as e:  # noqa: BLE001
                results[name] = f"failed: {e!r}"
        return results


dispatcher = NotificationDispatcher()
