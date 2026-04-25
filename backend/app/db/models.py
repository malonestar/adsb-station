"""SQLAlchemy 2.0 declarative models. All domain tables live here."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AircraftCatalog(Base):
    """One row per hex ever observed. Updated as new info arrives."""

    __tablename__ = "aircraft_catalog"

    hex: Mapped[str] = mapped_column(String(6), primary_key=True)
    registration: Mapped[str | None] = mapped_column(String(16))
    type_code: Mapped[str | None] = mapped_column(String(8))
    operator: Mapped[str | None] = mapped_column(String(128))
    owner: Mapped[str | None] = mapped_column(String(128))
    country: Mapped[str | None] = mapped_column(String(64))
    category: Mapped[str | None] = mapped_column(String(2))

    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    seen_count: Mapped[int] = mapped_column(Integer, default=1)

    max_alt_ft: Mapped[int | None] = mapped_column(Integer)
    max_speed_kt: Mapped[int | None] = mapped_column(Integer)
    min_distance_nm: Mapped[float | None] = mapped_column(Float)

    is_military: Mapped[bool] = mapped_column(Boolean, default=False)
    is_interesting: Mapped[bool] = mapped_column(Boolean, default=False)
    is_pia: Mapped[bool] = mapped_column(Boolean, default=False)

    photo_url: Mapped[str | None] = mapped_column(Text)
    photo_thumb_url: Mapped[str | None] = mapped_column(Text)
    photo_photographer: Mapped[str | None] = mapped_column(String(128))
    photo_link: Mapped[str | None] = mapped_column(Text)


class Position(Base):
    """Append-only history. Retention prunes older than N days."""

    __tablename__ = "positions"

    # SQLite auto-increments INTEGER PRIMARY KEY but NOT BIGINT — keep this as Integer.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hex: Mapped[str] = mapped_column(String(6), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    alt_baro: Mapped[int | None] = mapped_column(Integer)
    gs: Mapped[float | None] = mapped_column(Float)
    track: Mapped[float | None] = mapped_column(Float)
    baro_rate: Mapped[int | None] = mapped_column(Integer)
    rssi: Mapped[float | None] = mapped_column(Float)


Index("ix_positions_hex_ts", Position.hex, Position.ts)


class EnrichmentCache(Base):
    """Third-party API response cache. Key = (hex, source)."""

    __tablename__ = "enrichment_cache"

    hex: Mapped[str] = mapped_column(String(6), primary_key=True)
    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    http_status: Mapped[int | None] = mapped_column(Integer)


class DailyAggregate(Base):
    """One row per UTC day with summary stats."""

    __tablename__ = "daily_aggregates"

    date: Mapped[str] = mapped_column(String(10), primary_key=True)  # YYYY-MM-DD
    msgs_total: Mapped[int] = mapped_column(BigInteger, default=0)
    aircraft_unique: Mapped[int] = mapped_column(Integer, default=0)
    max_range_nm: Mapped[float] = mapped_column(Float, default=0.0)
    top_aircraft_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class PositionCellHourly(Base):
    """Pre-aggregated heatmap cells, populated hourly by app/stats/aggregates.py.

    Lookups go through raw SQL (single INSERT...SELECT for the rollup, single
    SELECT...GROUP BY for the heatmap query). The ORM model exists so
    Base.metadata.create_all builds the table in tests, and so future ORM
    consumers have typed access.
    """

    __tablename__ = "position_cells_hourly"

    hour_bucket: Mapped[str] = mapped_column(String(13), primary_key=True)  # YYYY-MM-DDTHH
    lat_cell: Mapped[float] = mapped_column(Float, primary_key=True)
    lon_cell: Mapped[float] = mapped_column(Float, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


Index("ix_pcells_hour", PositionCellHourly.hour_bucket)


class Alert(Base):
    """Active and historical alerts."""

    __tablename__ = "alerts"

    # SQLite auto-increments INTEGER PRIMARY KEY but NOT BIGINT.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hex: Mapped[str] = mapped_column(String(6), index=True)
    kind: Mapped[str] = mapped_column(String(32))  # military|emergency|watchlist|interesting
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    cleared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Watchlist(Base):
    """User-defined watch entries.

    `notify=True` means matches trigger Telegram/Discord notifications via the
    alert pipeline (the historical default for hex-kind entries). `notify=False`
    means matches still flag aircraft on the watchlist tab and surface in alert
    history, but no outbound push — the right default for high-volume kinds
    (operator/type) where every match would flood notifications.
    """

    __tablename__ = "watchlist"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16))  # hex|reg|type|operator
    value: Mapped[str] = mapped_column(String(128), index=True)
    label: Mapped[str | None] = mapped_column(String(128))
    notify: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FeedStatus(Base):
    """Per-feeder container health snapshot."""

    __tablename__ = "feed_status"

    feeder_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(16))  # ok|warn|down|unknown
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RouteCache(Base):
    """Per-callsign flight origin/destination cache.

    Fetched on-demand when the user opens the AircraftDetail panel. Falls back
    adsbdb → hexdb → AeroAPI. `source='not_found'` rows negative-cache misses
    for a short TTL so we don't hammer the APIs for unknown callsigns.
    """

    __tablename__ = "route_cache"

    # SQLite auto-increments INTEGER PRIMARY KEY but NOT BIGINT — keep as Integer.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    callsign: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    origin_icao: Mapped[str | None] = mapped_column(String(4))
    origin_iata: Mapped[str | None] = mapped_column(String(3))
    origin_name: Mapped[str | None] = mapped_column(String(128))
    origin_city: Mapped[str | None] = mapped_column(String(64))
    destination_icao: Mapped[str | None] = mapped_column(String(4))
    destination_iata: Mapped[str | None] = mapped_column(String(3))
    destination_name: Mapped[str | None] = mapped_column(String(128))
    destination_city: Mapped[str | None] = mapped_column(String(64))
    airline_name: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # adsbdb|hexdb|aeroapi|not_found
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CooldownOverride(Base):
    """Explicit cooldown extensions set via bot /mute reply.

    Takes precedence over the in-memory CooldownTracker for the given key until
    `until_at`. Expired rows are ignored (and cleaned by a periodic sweep if you
    want to add one — fine to skip for v1, just let them accumulate).
    """

    __tablename__ = "cooldown_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hex: Mapped[str] = mapped_column(String(8), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    until_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="telegram_reply"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("hex", "kind", name="uq_cooldown_override_hex_kind"),
    )


class TelegramMessageMap(Base):
    """Maps outbound Telegram alert message_ids → aircraft so replies can act on them.

    When the TelegramNotifier sends an alert, it stores (chat_id, message_id) along
    with the hex/callsign/kind metadata. When the user replies to the alert, the bot
    looks up this mapping to know which aircraft the reply refers to.
    """

    __tablename__ = "telegram_message_map"

    # SQLite auto-increments INTEGER PRIMARY KEY but NOT BIGINT — keep this as Integer.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Telegram chat/message IDs can exceed 32-bit range, so store as BigInteger.
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    hex: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    callsign: Mapped[str | None] = mapped_column(String(16), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("chat_id", "message_id", name="uq_tg_chat_message"),
    )
