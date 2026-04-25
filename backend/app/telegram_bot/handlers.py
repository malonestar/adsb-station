"""Command + reply handlers for the interactive Telegram bot.

Handlers return either a plain HTML string or a `BotReply` dataclass. The bot
poller treats a string as text-only (`sendMessage`) and a `BotReply` with a
`photo_url` as a photo-with-caption (`sendPhoto`) — falling back to sendMessage
if the photo fetch fails. Database and service access goes through the existing
app modules — no new infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape as html_escape
from typing import Any

from sqlalchemy import delete, desc, select

from app.alerts.watchlist import watchlist
from app.config import settings
from app.db.models import AircraftCatalog, Alert, TelegramMessageMap, Watchlist as WatchlistRow
from app.db.session import session_scope
from app.enrichment import planespotters
from app.enrichment.route import route_service
from app.logging import get_logger
from app.notifications import dispatcher as dispatcher_module
from app.readsb.poller import ReadsbPoller
from app.readsb.schema import AircraftState
from app.stats.live import live_stats


@dataclass
class BotReply:
    """Structured bot response. `photo_url` opts into Telegram sendPhoto.

    If `photo_url` is set, the poller calls sendPhoto with `text` as the caption.
    Otherwise it calls sendMessage with `text`. Handlers that never emit photos
    can continue to return a plain string — the poller treats that as text-only.
    """

    text: str
    photo_url: str | None = None

log = get_logger(__name__)


# Vocabulary for reply-to-alert actions. Matched case-insensitively against
# reply text (after stripping). Also accepts these emojis by themselves.
_REPLY_WATCH = {"watch", "watchlist", "add", "star", "⭐", "👀"}
_REPLY_MUTE = {"mute", "silence", "quiet", "🔇", "🔕"}
_REPLY_INFO = {"info", "details", "what", "?"}

_VALID_HEX = set("0123456789abcdef")

# Extends the (hex, kind) cooldown by this much when a user replies "mute".
_MUTE_EXTEND_HOURS = 24


def _is_valid_hex(s: str) -> bool:
    s = s.strip().lower()
    if len(s) != 6:
        return False
    return all(c in _VALID_HEX for c in s)


def _esc(s: Any) -> str:
    """HTML-escape for Telegram's HTML parse mode. None → ''."""
    if s is None:
        return ""
    return html_escape(str(s), quote=False)


def _fmt_age(delta: timedelta) -> str:
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m ago"
    hrs = mins // 60
    if hrs < 24:
        return f"{hrs}h ago"
    days = hrs // 24
    return f"{days}d ago"


class CommandRouter:
    def __init__(self, poller: ReadsbPoller | None = None) -> None:
        # Poller is optional for ease of testing — a missing poller makes
        # /status and /nearest report "live data unavailable".
        self._poller = poller

    def set_poller(self, poller: ReadsbPoller) -> None:
        self._poller = poller

    # ─────────────────────────────────────────────────────────────────────
    # Entry points
    # ─────────────────────────────────────────────────────────────────────

    async def handle_command(
        self, text: str, chat_id: int
    ) -> "str | BotReply | None":
        """Dispatch a /slash command. Returns the reply (HTML text or BotReply) or None."""
        text = text.strip()
        if not text.startswith("/"):
            return None
        parts = text.split(maxsplit=1)
        # Telegram includes the bot username for group mentions, e.g. /status@ADSB_ms_bot
        head = parts[0].lower()
        if "@" in head:
            head = head.split("@", 1)[0]
        args = parts[1] if len(parts) > 1 else ""

        try:
            if head == "/help" or head == "/start":
                return self._help_text()
            if head == "/status":
                return await self._cmd_status()
            if head == "/nearest":
                return await self._cmd_nearest()
            if head == "/last":
                return await self._cmd_last(args)
            if head == "/watch":
                return await self._cmd_watch(args)
            if head == "/unwatch":
                return await self._cmd_unwatch(args)
            return (
                f"Unknown command <code>{_esc(head)}</code>.\n"
                f"Use /help for the list of commands."
            )
        except Exception as e:  # noqa: BLE001
            log.exception("telegram_command_error", command=head)
            return f"Sorry, that failed: <code>{_esc(str(e))}</code>"

    async def handle_reply(
        self,
        original_message_id: int,
        chat_id: int,
        reply_text: str,
        reply_to_text: str | None = None,
    ) -> "str | BotReply | None":
        """Handle a reply to an alert message.

        Looks up (chat_id, original_message_id) in telegram_message_map.
        If found, parses the reply vocabulary and performs the action.
        If not found, tries to glean a hex from the quoted message text and
        suggests the manual /watch command.
        """
        try:
            mapping = await self._lookup_message_map(chat_id, original_message_id)
            reply_clean = (reply_text or "").strip()
            reply_lower = reply_clean.lower()
            if mapping is None:
                # Message pre-dates the map, or was pruned. Try to salvage.
                gleaned = _glean_hex_from_text(reply_to_text)
                hint = (
                    f" I think the aircraft was <code>{_esc(gleaned)}</code> — "
                    f"use /watch {_esc(gleaned)} &lt;label&gt; to add it manually."
                    if gleaned
                    else ""
                )
                return (
                    "I don't have a mapping for that message anymore (too old or "
                    "pre-dates the bot). " + hint
                )
            hex_code = mapping.hex
            callsign = mapping.callsign
            kind = mapping.kind

            if reply_lower in _REPLY_WATCH or any(
                tok in reply_lower for tok in _REPLY_WATCH
            ):
                return await self._reply_watch(hex_code, callsign)
            if reply_lower in _REPLY_MUTE or any(
                tok in reply_lower for tok in _REPLY_MUTE
            ):
                return await self._reply_mute(hex_code, kind)
            if reply_lower in _REPLY_INFO or any(
                tok in reply_lower for tok in _REPLY_INFO
            ):
                return await self._reply_info(hex_code, callsign)

            return (
                "I didn't understand that. Reply with <b>watch</b>, <b>mute</b>, "
                "or <b>info</b>. Try /help for all commands."
            )
        except Exception as e:  # noqa: BLE001
            log.exception("telegram_reply_error")
            return f"Sorry, that failed: <code>{_esc(str(e))}</code>"

    # ─────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _help_text() -> str:
        return (
            "<b>ADS-B Bot Commands</b>\n"
            "/status — station status\n"
            "/nearest — closest aircraft right now\n"
            "/last [N] — last N alerts (default 5)\n"
            "/watch HEX [label] — add to watchlist\n"
            "/unwatch HEX — remove from watchlist\n"
            "/help — this message\n"
            "\n"
            "<b>Reply to any alert:</b>\n"
            "• \"watch\" / \"add\" / ⭐ — add to watchlist\n"
            "• \"mute\" / 🔇 — extend cooldown 24h\n"
            "• \"info\" — show position + route"
        )

    # ─────────────────────────────────────────────────────────────────────
    # Commands
    # ─────────────────────────────────────────────────────────────────────

    async def _cmd_status(self) -> str:
        if self._poller is None:
            return "🛩 <b>STATION STATUS</b>\nLive data unavailable (poller not started)."
        states = self._poller.current()
        snap = live_stats.snapshot(states, datetime.now(UTC))

        with_pos = snap.get("aircraft_with_position", 0)
        total = snap.get("aircraft_total", 0)
        msgs = snap.get("messages_per_sec", 0.0)
        max_range = snap.get("max_range_nm_today", 0.0)

        # Approximate SNR from the live histogram's weighted mean RSSI + a
        # rough estimate of noise floor from the weakest non-empty bucket.
        snr_str = _compute_snr_from_histogram(snap.get("signal_histogram") or [])

        return (
            "🛩 <b>STATION STATUS</b>\n"
            f"Aircraft: <code>{total}</code> ({with_pos} with position)\n"
            f"Msgs/sec: <code>{msgs}</code>\n"
            f"Max range today: <code>{max_range:g} nm</code>\n"
            f"SNR (est): <code>{snr_str}</code>"
        )

    async def _cmd_nearest(self) -> "str | BotReply":
        if self._poller is None:
            return "No live poller available."
        states = self._poller.current()
        with_pos = [
            s
            for s in states
            if s.distance_nm is not None
        ]
        if not with_pos:
            return "No aircraft with position reports in range right now."
        nearest = min(with_pos, key=lambda s: s.distance_nm or float("inf"))
        text = await self._format_aircraft(nearest, header="✈ <b>CLOSEST AIRCRAFT</b>")
        photo_url = await self._lookup_photo_url(nearest.hex)
        return BotReply(text=text, photo_url=photo_url)

    async def _cmd_last(self, args: str) -> str:
        count = 5
        if args.strip():
            try:
                n = int(args.strip().split()[0])
                count = max(1, min(20, n))
            except ValueError:
                return f"Can't parse count from <code>{_esc(args)}</code>. Try /last 10."
        async with session_scope() as s:
            rows = (
                await s.execute(
                    select(Alert).order_by(desc(Alert.triggered_at)).limit(count)
                )
            ).scalars().all()
        if not rows:
            return "🔔 No alerts yet."
        now = datetime.now(UTC)
        lines = [f"🔔 <b>LAST {len(rows)} ALERT{'S' if len(rows) != 1 else ''}</b>"]
        for r in rows:
            # SQLite strips tzinfo on read — re-attach UTC for age computation.
            trig = r.triggered_at
            if trig.tzinfo is None:
                trig = trig.replace(tzinfo=UTC)
            payload = r.payload or {}
            flight = payload.get("flight") or ""
            age = _fmt_age(now - trig)
            # Alignment-free: one line per alert
            flight_part = f" {_esc(flight)}" if flight else ""
            lines.append(
                f"• <code>{_esc(r.hex)}</code>{flight_part}  {_esc(r.kind)}  {age}"
            )
        return "\n".join(lines)

    async def _cmd_watch(self, args: str) -> str:
        parts = args.strip().split(maxsplit=1)
        if not parts:
            return "Usage: /watch HEX [label]"
        hex_code = parts[0].strip().lower()
        label = parts[1].strip() if len(parts) > 1 else None
        if not _is_valid_hex(hex_code):
            return (
                f"<code>{_esc(hex_code)}</code> doesn't look like a 6-char hex code. "
                f"Example: /watch a835af Musk"
            )
        return await self._watchlist_add(hex_code, label, source="command")

    async def _cmd_unwatch(self, args: str) -> str:
        parts = args.strip().split()
        if not parts:
            return "Usage: /unwatch HEX"
        hex_code = parts[0].strip().lower()
        if not _is_valid_hex(hex_code):
            return f"<code>{_esc(hex_code)}</code> doesn't look like a 6-char hex code."
        async with session_scope() as s:
            r = await s.execute(
                delete(WatchlistRow).where(
                    WatchlistRow.kind == "hex", WatchlistRow.value == hex_code
                )
            )
            deleted = r.rowcount or 0
        if deleted:
            await watchlist.refresh()
            return f"✅ Removed <code>{_esc(hex_code)}</code> from watchlist."
        return f"<code>{_esc(hex_code)}</code> wasn't on the watchlist."

    # ─────────────────────────────────────────────────────────────────────
    # Reply handlers
    # ─────────────────────────────────────────────────────────────────────

    async def _reply_watch(self, hex_code: str, callsign: str | None) -> str:
        label = callsign or "bot-added (reply)"
        return await self._watchlist_add(hex_code, label, source="reply")

    async def _reply_mute(self, hex_code: str, kind: str) -> str:
        """Persistently mute (hex, kind) for 24h via the cooldown_overrides table.

        Writes a row to the DB and updates the dispatcher's in-memory override
        cache so the mute survives a backend restart.
        """
        dispatcher = dispatcher_module.dispatcher
        tracker = getattr(dispatcher, "_cooldown", None)
        if tracker is None:
            return "Cooldown tracker unavailable — can't mute right now."
        until = datetime.now(UTC) + timedelta(hours=_MUTE_EXTEND_HOURS)
        await tracker.set_override(
            hex_code, kind, until_at=until, source="telegram_reply"
        )
        return (
            f"🔇 Muted <code>{_esc(hex_code)}</code> ({_esc(kind)}) "
            f"for {_MUTE_EXTEND_HOURS}h."
        )

    async def _reply_info(self, hex_code: str, callsign: str | None) -> "str | BotReply":
        state: AircraftState | None = None
        if self._poller is not None:
            state = next(
                (s for s in self._poller.current() if s.hex == hex_code), None
            )
        if state is None:
            return (
                f"Aircraft <code>{_esc(hex_code)}</code> isn't currently in range. "
                f"Try /last to see recent alerts."
            )
        text = await self._format_aircraft(
            state, header=f"ℹ <b>{_esc(hex_code.upper())}</b>"
        )
        photo_url = await self._lookup_photo_url(hex_code)
        return BotReply(text=text, photo_url=photo_url)

    # ─────────────────────────────────────────────────────────────────────
    # Shared helpers
    # ─────────────────────────────────────────────────────────────────────

    async def _lookup_message_map(
        self, chat_id: int, message_id: int
    ) -> TelegramMessageMap | None:
        async with session_scope() as s:
            return (
                await s.execute(
                    select(TelegramMessageMap)
                    .where(
                        TelegramMessageMap.chat_id == chat_id,
                        TelegramMessageMap.message_id == message_id,
                    )
                )
            ).scalar_one_or_none()

    async def _watchlist_add(
        self, hex_code: str, label: str | None, *, source: str
    ) -> str:
        async with session_scope() as s:
            existing = (
                await s.execute(
                    select(WatchlistRow).where(
                        WatchlistRow.kind == "hex",
                        WatchlistRow.value == hex_code,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return (
                    f"<code>{_esc(hex_code)}</code> is already on the watchlist "
                    f"({_esc(existing.label or 'no label')})."
                )
            s.add(
                WatchlistRow(
                    kind="hex",
                    value=hex_code,
                    label=label,
                    created_at=datetime.now(UTC),
                )
            )
        await watchlist.refresh()
        label_part = f" — <i>{_esc(label)}</i>" if label else ""
        log.info(
            "telegram_watchlist_added", hex=hex_code, label=label, source=source
        )
        return f"✅ Added <code>{_esc(hex_code)}</code> to watchlist{label_part}."

    async def _lookup_photo_url(self, hex_code: str) -> str | None:
        """Return a photo URL for the given hex, or None if unavailable.

        Prefers the photo already stored in `aircraft_catalog` (enrichment
        coordinator populates this). Falls back to a fresh Planespotters lookup
        only if the catalog has no cached photo yet. Never raises.
        """
        hex_code = hex_code.lower()
        try:
            async with session_scope() as s:
                cat = (
                    await s.execute(
                        select(AircraftCatalog).where(AircraftCatalog.hex == hex_code)
                    )
                ).scalar_one_or_none()
            if cat is not None and cat.photo_url:
                return cat.photo_url
        except Exception:  # noqa: BLE001
            log.warning("photo_catalog_lookup_failed", hex=hex_code)
        # Nothing in the catalog — try a direct planespotters lookup. The
        # planespotters module has its own circuit breaker + cache so this is
        # cheap on repeat calls.
        try:
            photo = await planespotters.lookup(hex_code)
            if photo is not None:
                return photo.get("photo_url") or photo.get("photo_thumb_url")
        except Exception:  # noqa: BLE001
            log.warning("photo_planespotters_lookup_failed", hex=hex_code)
        return None

    async def _format_aircraft(
        self, state: AircraftState, *, header: str
    ) -> str:
        """Build the HTML message body. Photo is attached separately by the
        caller via BotReply.photo_url and sendPhoto-with-caption."""
        flight = state.flight or "—"
        reg = state.registration or "—"
        type_code = state.type_code or "—"
        alt = state.alt_baro
        alt_str = f"{alt:,} ft" if alt is not None else "—"
        gs = state.gs
        gs_str = f"{gs:.0f} kt" if gs is not None else "—"
        track = state.track
        track_str = f"{track:.0f}°" if track is not None else "—"
        dist = state.distance_nm
        dist_str = f"{dist:.1f} nm" if dist is not None else "—"

        route_line = ""
        if state.flight:
            try:
                route = await route_service.get_route(state.flight)
                if (
                    route is not None
                    and route.source != "not_found"
                    and route.origin is not None
                    and route.destination is not None
                ):
                    route_line = (
                        f"\n{_esc(route.origin.icao)} → "
                        f"{_esc(route.destination.icao)}  "
                        f"<i>(via {_esc(route.source)})</i>"
                    )
            except Exception:  # noqa: BLE001
                log.warning("route_lookup_failed_in_bot", callsign=state.flight)

        subtitle_parts: list[str] = []
        if state.flight:
            subtitle_parts.append(f"<b>{_esc(flight)}</b>")
        extras: list[str] = []
        if reg != "—":
            extras.append(_esc(reg))
        if type_code != "—":
            extras.append(_esc(type_code))
        subtitle = " ".join(subtitle_parts)
        if extras:
            subtitle += f" ({' · '.join(extras)})" if subtitle else f"({' · '.join(extras)})"

        return (
            f"{header}\n"
            f"{subtitle or '(no callsign)'}"
            f"{route_line}\n"
            f"{dist_str} · {alt_str} · {gs_str} · {track_str}\n"
            f"Hex: <code>{_esc(state.hex)}</code>"
        )


# ─────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────


def _compute_snr_from_histogram(hist: list[dict[str, Any]]) -> str:
    """Rough SNR estimate: weighted mean RSSI minus noise floor (-35 dBFS)."""
    non_empty = [h for h in hist if (h.get("count") or 0) > 0]
    if not non_empty:
        return "—"
    total = sum(h["count"] for h in non_empty)
    mean = sum(h["bucket"] * h["count"] for h in non_empty) / total
    noise = -35  # conservative estimate — real value is logged by the exporter
    return f"{(mean - noise):.1f} dB"


def _glean_hex_from_text(text: str | None) -> str | None:
    """Best-effort extract a 6-char hex token from an alert message body.

    Our alerts have a 'Hex: abcdef' line. This pulls the first 6-hex-char
    sequence that looks like an ICAO hex code. Nothing is guaranteed.
    """
    if not text:
        return None
    import re

    # Look for 'Hex: xxxxxx' or a standalone 6-hex-char token
    match = re.search(r"Hex:\s*([0-9a-fA-F]{6})", text)
    if match:
        return match.group(1).lower()
    match = re.search(r"\b([0-9a-fA-F]{6})\b", text)
    if match:
        candidate = match.group(1).lower()
        # Guard against random 6-digit numbers being picked up
        if any(c in "abcdef" for c in candidate):
            return candidate
    return None
