"""Async SQLAlchemy engine + session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

_DB_URL = f"sqlite+aiosqlite:///{settings.db_path}"

engine = create_async_engine(
    _DB_URL,
    echo=False,
    future=True,
    connect_args={"timeout": 30},
)

SessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional scope. Commits on exit, rolls back on exception."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency."""
    async with session_scope() as s:
        yield s


async def enable_wal() -> None:
    """Apply SQLite pragmas for WAL + tuning. Call once at app startup."""
    async with engine.begin() as conn:
        for pragma in (
            "PRAGMA journal_mode=WAL",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA temp_store=MEMORY",
            "PRAGMA cache_size=-65536",   # 64 MB
            "PRAGMA foreign_keys=ON",
            "PRAGMA busy_timeout=30000",
        ):
            await conn.exec_driver_sql(pragma)
