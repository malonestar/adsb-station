"""Telegram bot long-polling loop.

Runs forever in a background asyncio task. Polls Telegram's getUpdates API
with a 30s long-poll. Only accepts messages from the authorized chat_id.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.logging import get_logger
from app.readsb.poller import ReadsbPoller
from app.telegram_bot.handlers import BotReply, CommandRouter

log = get_logger(__name__)


class TelegramBot:
    def __init__(
        self,
        token: str,
        chat_id: int,
        poller: ReadsbPoller | None = None,
    ) -> None:
        self._token = token
        self._chat_id = chat_id  # only accept commands from this chat
        self._offset = 0
        self._stop = asyncio.Event()
        self._handlers = CommandRouter(poller=poller)

    def set_poller(self, poller: ReadsbPoller) -> None:
        """Attach the readsb poller after both components have started."""
        self._handlers.set_poller(poller)

    async def run(self) -> None:
        """Long-polling loop. Runs forever until stop() is called.

        Uses a 30-second long poll window so the server holds the connection
        open until there's an update (or the window elapses), which is far
        more efficient than short polling.
        """
        base = f"https://api.telegram.org/bot{self._token}"
        log.info("telegram_bot_starting", chat_id=self._chat_id)
        # Timeout: the API long-poll is 30s; we give httpx a few seconds of slack
        # to receive the response and then give up and retry.
        async with httpx.AsyncClient(timeout=60) as client:
            while not self._stop.is_set():
                try:
                    r = await client.get(
                        f"{base}/getUpdates",
                        params={
                            "offset": self._offset,
                            "timeout": 30,
                            # allowed_updates must be a JSON-encoded array as a
                            # string query parameter — Telegram's API spec is explicit.
                            "allowed_updates": '["message"]',
                        },
                    )
                    data = r.json()
                    if not data.get("ok", False):
                        log.warning(
                            "telegram_api_not_ok",
                            description=data.get("description"),
                        )
                        await asyncio.sleep(5)
                        continue
                    for update in data.get("result", []):
                        self._offset = max(self._offset, update["update_id"] + 1)
                        try:
                            await self._process_update(update, client, base)
                        except Exception:  # noqa: BLE001
                            log.exception(
                                "telegram_process_update_error",
                                update_id=update.get("update_id"),
                            )
                except httpx.HTTPError as e:
                    log.warning("telegram_poll_http_error", error=str(e))
                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    log.exception("telegram_poll_unexpected", error=str(e))
                    await asyncio.sleep(5)
        log.info("telegram_bot_stopped")

    async def stop(self) -> None:
        self._stop.set()

    async def _process_update(
        self, update: dict[str, Any], client: httpx.AsyncClient, base: str
    ) -> None:
        msg = update.get("message")
        if not msg:
            return
        chat_id = msg.get("chat", {}).get("id")
        if chat_id != self._chat_id:
            log.info("telegram_rejected_unauthorized", chat_id=chat_id)
            return

        text = (msg.get("text") or "").strip()
        reply_to = msg.get("reply_to_message")

        response: str | BotReply | None = None
        if reply_to:
            reply_to_text = reply_to.get("text") or reply_to.get("caption")
            response = await self._handlers.handle_reply(
                reply_to["message_id"],
                chat_id,
                text,
                reply_to_text=reply_to_text,
            )
        elif text.startswith("/"):
            response = await self._handlers.handle_command(text, chat_id)
        else:
            # Plain non-command, non-reply message — ignore silently.
            return

        if not response:
            return

        reply_to_id = msg["message_id"]
        if isinstance(response, BotReply) and response.photo_url:
            sent = await self._send_photo(
                client,
                base,
                chat_id,
                photo_url=response.photo_url,
                caption=response.text,
                reply_to_message_id=reply_to_id,
            )
            if not sent:
                # sendPhoto failed (e.g. photo URL 404) — fall back to text-only.
                await self._send(
                    client,
                    base,
                    chat_id,
                    response.text,
                    reply_to_message_id=reply_to_id,
                )
        else:
            response_text = (
                response.text if isinstance(response, BotReply) else response
            )
            await self._send(
                client,
                base,
                chat_id,
                response_text,
                reply_to_message_id=reply_to_id,
            )

    async def _send(
        self,
        client: httpx.AsyncClient,
        base: str,
        chat_id: int,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> None:
        try:
            body: dict[str, Any] = {
                "chat_id": chat_id,
                "text": text[:4096],
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            if reply_to_message_id is not None:
                body["reply_to_message_id"] = reply_to_message_id
            r = await client.post(f"{base}/sendMessage", json=body)
            if r.status_code >= 400:
                log.warning(
                    "telegram_send_http_error",
                    status=r.status_code,
                    body=r.text[:200],
                )
        except httpx.HTTPError as e:
            log.warning("telegram_send_error", error=str(e))

    async def _send_photo(
        self,
        client: httpx.AsyncClient,
        base: str,
        chat_id: int,
        *,
        photo_url: str,
        caption: str,
        reply_to_message_id: int | None = None,
    ) -> bool:
        """POST sendPhoto with a caption. Returns True on success.

        Telegram fetches the photo URL itself; if the URL returns 4xx/5xx, the
        API returns 400. On any failure we return False so the caller can fall
        back to sendMessage.
        """
        try:
            body: dict[str, Any] = {
                "chat_id": chat_id,
                "photo": photo_url,
                # Telegram caption length cap is 1024.
                "caption": caption[:1024],
                "parse_mode": "HTML",
            }
            if reply_to_message_id is not None:
                body["reply_to_message_id"] = reply_to_message_id
            r = await client.post(f"{base}/sendPhoto", json=body)
            if r.status_code >= 400:
                log.warning(
                    "telegram_send_photo_http_error",
                    status=r.status_code,
                    body=r.text[:200],
                    photo_url=photo_url,
                )
                return False
            return True
        except httpx.HTTPError as e:
            log.warning("telegram_send_photo_error", error=str(e))
            return False
