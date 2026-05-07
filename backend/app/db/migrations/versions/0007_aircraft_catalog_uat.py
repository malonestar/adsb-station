"""aircraft_catalog.ever_seen_uat — sticky UAT-band sighting flag.

Set by the enrichment coordinator the first tick a state arrives with
`uat_version` populated. Lets the catalog UI filter to aircraft we've ever
caught via 978 MHz UAT (mostly US GA below 18k ft).

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Default existing rows to False — we have no historical UAT data, so the
    # flag will only flip True for aircraft observed via UAT going forward.
    op.add_column(
        "aircraft_catalog",
        sa.Column("ever_seen_uat", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    with op.batch_alter_table("aircraft_catalog") as batch:
        batch.alter_column("ever_seen_uat", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("aircraft_catalog") as batch:
        batch.drop_column("ever_seen_uat")
