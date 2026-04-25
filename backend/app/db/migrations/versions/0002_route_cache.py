"""route_cache table

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-23 22:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "route_cache",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("callsign", sa.String(16), nullable=False, unique=True),
        sa.Column("origin_icao", sa.String(4)),
        sa.Column("origin_iata", sa.String(3)),
        sa.Column("origin_name", sa.String(128)),
        sa.Column("origin_city", sa.String(64)),
        sa.Column("destination_icao", sa.String(4)),
        sa.Column("destination_iata", sa.String(3)),
        sa.Column("destination_name", sa.String(128)),
        sa.Column("destination_city", sa.String(64)),
        sa.Column("airline_name", sa.String(64)),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_route_cache_callsign", "route_cache", ["callsign"])


def downgrade() -> None:
    op.drop_index("ix_route_cache_callsign", table_name="route_cache")
    op.drop_table("route_cache")
