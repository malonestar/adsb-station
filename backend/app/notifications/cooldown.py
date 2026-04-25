"""Per-hex-per-kind cooldown to prevent notification spam.

The primary mechanism is an in-memory dict of (hex, kind) -> last_allowed_at
with a TTL. On top of that, we support **persistent overrides** — rows in the
`cooldown_overrides` table written by the interactive Telegram bot when the user
replies "mute" to an alert. Overrides take precedence over the TTL logic:
while an override is active (until_at > now), `allow()` always returns False
(unless bypass=True for emergencies).

Overrides survive backend restarts; the TTL dict does not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.models import CooldownOverride
from app.db.session import session_scope
from app.logging import get_logger

if TYPE_CHECKING:
    pass

log = get_logger(__name__)


class CooldownTracker:
    """Tracks the last 'allow' timestamp for each (hex, kind) pair."""

    def __init__(self, ttl: timedelta) -> None:
        self._ttl = ttl
        self._last: dict[tuple[str, str], datetime] = {}
        # In-memory mirror of the persistent `cooldown_overrides` table. Keyed by
        # (hex, kind) -> until_at. Hot-path reads consult this dict only; writes
        # go to both the dict and the DB. Populated on load_overrides().
        self._overrides: dict[tuple[str, str], datetime] = {}

    async def load_overrides(self) -> None:
        """One-shot load of non-expired override rows into memory.

        Call once at startup (after migrations have run). Rows whose `until_at`
        is already in the past are skipped. Safe to call multiple times; each
        call replaces the cache wholesale.
        """
        now = datetime.now(UTC)
        try:
            async with session_scope() as s:
                rows = (
                    await s.execute(
                        select(CooldownOverride).where(CooldownOverride.until_at > now)
                    )
                ).scalars().all()
            new_cache: dict[tuple[str, str], datetime] = {}
            for r in rows:
                until = r.until_at
                if until.tzinfo is None:
                    until = until.replace(tzinfo=UTC)
                new_cache[(r.hex, r.kind)] = until
            self._overrides = new_cache
            log.info("cooldown_overrides_loaded", count=len(new_cache))
        except Exception as e:  # noqa: BLE001
            # Don't let a missing table (pre-migration bootstrap) kill startup.
            log.warning("cooldown_overrides_load_failed", error=str(e))

    def _override_active(self, key: tuple[str, str], now: datetime) -> bool:
        """Return True if (hex, kind) currently has an active override."""
        until = self._overrides.get(key)
        if until is None:
            return False
        if until.tzinfo is None:
            until = until.replace(tzinfo=UTC)
        if until <= now:
            # Expired — clean up the in-memory entry lazily. The DB row will be
            # swept on the next restart / load_overrides() if needed.
            self._overrides.pop(key, None)
            return False
        return True

    def allow(self, hex_code: str, kind: str, now: datetime, *, bypass: bool = False) -> bool:
        """Return True if a notification for (hex, kind) should fire now.

        Always returns True when bypass=True (for emergencies). When a persistent
        override is active (see load_overrides / set_override), returns False.
        Otherwise applies the TTL-based logic.
        """
        key = (hex_code, kind)
        if bypass:
            self._last[key] = now
            return True
        if self._override_active(key, now):
            return False
        last = self._last.get(key)
        if last is None or (now - last) >= self._ttl:
            self._last[key] = now
            return True
        return False

    async def set_override(
        self,
        hex_code: str,
        kind: str,
        *,
        until_at: datetime,
        source: str = "telegram_reply",
    ) -> None:
        """Upsert a persistent cooldown override.

        Writes to both the in-memory cache and the `cooldown_overrides` table
        so the mute survives a backend restart. Existing rows for the same
        (hex, kind) are replaced.
        """
        if until_at.tzinfo is None:
            until_at = until_at.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        key = (hex_code, kind)
        # Update in-memory cache first. Even if the DB write fails below we
        # want the current process to honor the mute.
        self._overrides[key] = until_at
        try:
            async with session_scope() as s:
                stmt = (
                    sqlite_insert(CooldownOverride)
                    .values(
                        hex=hex_code,
                        kind=kind,
                        until_at=until_at,
                        source=source,
                        created_at=now,
                    )
                    .on_conflict_do_update(
                        index_elements=["hex", "kind"],
                        set_={
                            "until_at": until_at,
                            "source": source,
                            "created_at": now,
                        },
                    )
                )
                await s.execute(stmt)
            log.info(
                "cooldown_override_set",
                hex=hex_code,
                kind=kind,
                until_at=until_at.isoformat(),
                source=source,
            )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "cooldown_override_persist_failed",
                hex=hex_code,
                kind=kind,
                error=str(e),
            )

    async def clear_override(self, hex_code: str, kind: str) -> None:
        """Remove any active override for (hex, kind). Idempotent."""
        key = (hex_code, kind)
        self._overrides.pop(key, None)
        try:
            async with session_scope() as s:
                await s.execute(
                    delete(CooldownOverride).where(
                        CooldownOverride.hex == hex_code,
                        CooldownOverride.kind == kind,
                    )
                )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "cooldown_override_clear_failed",
                hex=hex_code,
                kind=kind,
                error=str(e),
            )

    def __len__(self) -> int:
        return len(self._last)
