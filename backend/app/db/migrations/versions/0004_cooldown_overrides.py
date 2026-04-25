"""cooldown_overrides table

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-24 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cooldown_overrides",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("hex", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("until_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "source",
            sa.String(32),
            nullable=False,
            server_default="telegram_reply",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("hex", "kind", name="uq_cooldown_override_hex_kind"),
    )


def downgrade() -> None:
    op.drop_table("cooldown_overrides")
