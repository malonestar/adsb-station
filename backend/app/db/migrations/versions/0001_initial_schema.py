"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-19 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "aircraft_catalog",
        sa.Column("hex", sa.String(6), primary_key=True),
        sa.Column("registration", sa.String(16)),
        sa.Column("type_code", sa.String(8)),
        sa.Column("operator", sa.String(128)),
        sa.Column("owner", sa.String(128)),
        sa.Column("country", sa.String(64)),
        sa.Column("category", sa.String(2)),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seen_count", sa.Integer, default=1),
        sa.Column("max_alt_ft", sa.Integer),
        sa.Column("max_speed_kt", sa.Integer),
        sa.Column("min_distance_nm", sa.Float),
        sa.Column("is_military", sa.Boolean, default=False),
        sa.Column("is_interesting", sa.Boolean, default=False),
        sa.Column("is_pia", sa.Boolean, default=False),
        sa.Column("photo_url", sa.Text),
        sa.Column("photo_thumb_url", sa.Text),
        sa.Column("photo_photographer", sa.String(128)),
        sa.Column("photo_link", sa.Text),
    )

    op.create_table(
        "positions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("hex", sa.String(6), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("lon", sa.Float, nullable=False),
        sa.Column("alt_baro", sa.Integer),
        sa.Column("gs", sa.Float),
        sa.Column("track", sa.Float),
        sa.Column("baro_rate", sa.Integer),
        sa.Column("rssi", sa.Float),
    )
    op.create_index("ix_positions_hex", "positions", ["hex"])
    op.create_index("ix_positions_ts", "positions", ["ts"])
    op.create_index("ix_positions_hex_ts", "positions", ["hex", "ts"])

    op.create_table(
        "enrichment_cache",
        sa.Column("hex", sa.String(6), primary_key=True),
        sa.Column("source", sa.String(32), primary_key=True),
        sa.Column("payload_json", sa.JSON, nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("http_status", sa.Integer),
    )

    op.create_table(
        "daily_aggregates",
        sa.Column("date", sa.String(10), primary_key=True),
        sa.Column("msgs_total", sa.BigInteger, default=0),
        sa.Column("aircraft_unique", sa.Integer, default=0),
        sa.Column("max_range_nm", sa.Float, default=0.0),
        sa.Column("top_aircraft_json", sa.JSON, default=dict),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("hex", sa.String(6), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cleared_at", sa.DateTime(timezone=True)),
        sa.Column("payload", sa.JSON, default=dict),
    )
    op.create_index("ix_alerts_hex", "alerts", ["hex"])
    op.create_index("ix_alerts_triggered_at", "alerts", ["triggered_at"])

    op.create_table(
        "watchlist",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("value", sa.String(128), nullable=False),
        sa.Column("label", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_watchlist_value", "watchlist", ["value"])

    op.create_table(
        "feed_status",
        sa.Column("feeder_name", sa.String(64), primary_key=True),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("last_ok_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("feed_status")
    op.drop_table("watchlist")
    op.drop_table("alerts")
    op.drop_table("daily_aggregates")
    op.drop_table("enrichment_cache")
    op.drop_table("positions")
    op.drop_table("aircraft_catalog")
