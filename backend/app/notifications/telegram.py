"""Telegram bot adapter. Uses the Bot API directly via httpx (no python-telegram-bot dep).

Enabled when both ADSB_TELEGRAM_BOT_TOKEN and ADSB_TELEGRAM_CHAT_ID are set.

When an alert is sent, the Telegram API response includes `result.message_id`. We
capture that and persist a row to `telegram_message_map` so that if the user replies
to the alert message later, the bot (see `app.telegram_bot`) can look up which
aircraft the reply refers to. If the map-write fails, alert delivery still succeeds
— the interactive reply feature is best-effort, never a regression on delivery.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.db.models import TelegramMessageMap
from app.db.session import session_scope
from app.logging import get_logger
from app.notifications.formatter import FormattedMessage

log = get_logger(__name__)


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._base = f"https://api.telegram.org/bot{bot_token}"
        self._chat_id = chat_id

    @classmethod
    def maybe_create(cls, token: str | None, chat_id: str | None) -> "TelegramNotifier | None":
        if not token or not chat_id:
            return None
        return cls(token, chat_id)

    async def notify(
        self,
        msg: FormattedMessage,
        *,
        alert: dict[str, Any] | None = None,
    ) -> None:
        """Send the message. Prefers sendPhoto with caption when a photo is present.

        Raises httpx.HTTPError on transport/HTTP failure — the dispatcher
        catches + logs per-channel failures.

        When `alert` is provided (hex/kind/payload), the resulting Telegram
        message_id is persisted to `telegram_message_map` so replies can act on it.
        """
        # Telegram caption length cap is 1024 chars. Plain text message cap is 4096.
        # In practice our messages are <500 chars, but truncate defensively.
        async with httpx.AsyncClient(timeout=10.0) as client:
            if msg.photo_url:
                caption = msg.telegram_text[:1024]
                r = await client.post(
                    f"{self._base}/sendPhoto",
                    json={
                        "chat_id": self._chat_id,
                        "photo": msg.photo_url,
                        "caption": caption,
                        "parse_mode": "MarkdownV2",
                    },
                )
            else:
                r = await client.post(
                    f"{self._base}/sendMessage",
                    json={
                        "chat_id": self._chat_id,
                        "text": msg.telegram_text[:4096],
                        "parse_mode": "MarkdownV2",
                        "disable_web_page_preview": True,
                    },
                )
            r.raise_for_status()
            response_json: dict[str, Any] = {}
            try:
                response_json = r.json()
            except (ValueError, TypeError):
                pass

        log.info("telegram_notified", title=msg.title)

        # Persist mapping so replies can find the aircraft. Best-effort only —
        # if this fails (DB locked, schema missing pre-migration, etc.), the
        # alert is still delivered. Skip when we have no alert context (e.g.,
        # the synthetic test-send path).
        if alert is None:
            return
        message_id = None
        try:
            result = response_json.get("result") if isinstance(response_json, dict) else None
            if isinstance(result, dict):
                message_id = result.get("message_id")
        except Exception:  # noqa: BLE001
            message_id = None
        if message_id is None:
            log.warning("telegram_no_message_id_in_response")
            return
        try:
            chat_id_int = int(self._chat_id)
        except (TypeError, ValueError):
            log.warning("telegram_chat_id_not_int", chat_id=self._chat_id)
            return
        hex_code = str(alert.get("hex", "")).lower()
        if not hex_code:
            return
        payload = alert.get("payload") or {}
        callsign = payload.get("flight")
        if isinstance(callsign, str):
            callsign = callsign.strip() or None
        kind = str(alert.get("kind", "unknown"))
        try:
            async with session_scope() as s:
                s.add(
                    TelegramMessageMap(
                        chat_id=chat_id_int,
                        message_id=int(message_id),
                        hex=hex_code,
                        callsign=callsign,
                        kind=kind,
                        sent_at=datetime.now(UTC),
                    )
                )
        except Exception as e:  # noqa: BLE001
            # Absolutely never let a map-write failure break alert delivery.
            log.warning(
                "telegram_message_map_insert_failed",
                error=str(e),
                hex=hex_code,
                message_id=message_id,
            )

    @property
    def name(self) -> str:
        return "telegram"
