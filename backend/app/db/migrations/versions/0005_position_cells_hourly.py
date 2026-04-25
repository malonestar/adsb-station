"""position_cells_hourly — heatmap rollup table.

Pre-aggregates positions into (hour, lat_cell, lon_cell, count) so the
heatmap endpoint doesn't full-scan ~12M position rows on every cold fetch.
Cells are bucketed at the same 0.02° resolution the dashboard uses; other
grid values fall through to the live aggregation path.

Revision ID: 0005_position_cells_hourly
Revises: 0004_cooldown_overrides
Create Date: 2026-04-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "position_cells_hourly",
        sa.Column("hour_bucket", sa.String(13), primary_key=True),  # 'YYYY-MM-DDTHH'
        sa.Column("lat_cell", sa.Float, primary_key=True),
        sa.Column("lon_cell", sa.Float, primary_key=True),
        sa.Column("count", sa.Integer, nullable=False),
    )
    op.create_index(
        "ix_pcells_hour", "position_cells_hourly", ["hour_bucket"]
    )


def downgrade() -> None:
    op.drop_index("ix_pcells_hour", table_name="position_cells_hourly")
    op.drop_table("position_cells_hourly")
