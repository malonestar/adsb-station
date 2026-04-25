"""SQLite-backed TTL cache for enrichment responses."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select

from app.config import settings
from app.db.models import EnrichmentCache
from app.db.session import session_scope
from app.logging import get_logger

log = get_logger(__name__)


class EnrichmentCacheStore:
    async def get(self, hex_code: str, source: str) -> dict[str, Any] | None:
        async with session_scope() as s:
            row = await s.get(EnrichmentCache, (hex_code, source))
            if row is None:
                return None
            # SQLite strips tz info on read — coerce back to UTC-aware for comparison
            expires_at = row.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if expires_at < datetime.now(UTC):
                return None
            return row.payload_json

    async def set(
        self,
        hex_code: str,
        source: str,
        payload: dict[str, Any],
        *,
        ttl_days: int | None = None,
        http_status: int | None = None,
    ) -> None:
        now = datetime.now(UTC)
        expires = now + timedelta(days=ttl_days or settings.enrichment_ttl_days)
        async with session_scope() as s:
            existing = await s.get(EnrichmentCache, (hex_code, source))
            if existing:
                existing.payload_json = payload
                existing.fetched_at = now
                existing.expires_at = expires
                existing.http_status = http_status
            else:
                s.add(
                    EnrichmentCache(
                        hex=hex_code,
                        source=source,
                        payload_json=payload,
                        fetched_at=now,
                        expires_at=expires,
                        http_status=http_status,
                    )
                )

    async def invalidate(self, hex_code: str, source: str | None = None) -> None:
        async with session_scope() as s:
            stmt = delete(EnrichmentCache).where(EnrichmentCache.hex == hex_code)
            if source:
                stmt = stmt.where(EnrichmentCache.source == source)
            await s.execute(stmt)

    async def purge_expired(self) -> int:
        async with session_scope() as s:
            r = await s.execute(
                delete(EnrichmentCache).where(EnrichmentCache.expires_at < datetime.now(UTC))
            )
            return r.rowcount or 0


cache = EnrichmentCacheStore()
