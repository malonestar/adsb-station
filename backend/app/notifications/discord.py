"""Discord webhook adapter. No bot needed — just a webhook URL.

Enabled when ADSB_DISCORD_WEBHOOK_URL is set.
"""

from __future__ import annotations

import httpx

from app.logging import get_logger
from app.notifications.formatter import FormattedMessage

log = get_logger(__name__)


class DiscordNotifier:
    def __init__(self, webhook_url: str) -> None:
        self._url = webhook_url

    @classmethod
    def maybe_create(cls, webhook_url: str | None) -> "DiscordNotifier | None":
        if not webhook_url:
            return None
        return cls(webhook_url)

    async def notify(self, msg: FormattedMessage) -> None:
        payload = {"embeds": [msg.discord_embed]}
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(self._url, json=payload)
            r.raise_for_status()
        log.info("discord_notified", title=msg.title)

    @property
    def name(self) -> str:
        return "discord"
