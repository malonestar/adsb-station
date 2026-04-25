"""telegram_message_map table

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-24 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_message_map",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger, nullable=False),
        sa.Column("message_id", sa.BigInteger, nullable=False),
        sa.Column("hex", sa.String(8), nullable=False),
        sa.Column("callsign", sa.String(16), nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("chat_id", "message_id", name="uq_tg_chat_message"),
    )
    op.create_index(
        "ix_telegram_message_map_chat_id", "telegram_message_map", ["chat_id"]
    )
    op.create_index(
        "ix_telegram_message_map_message_id", "telegram_message_map", ["message_id"]
    )
    op.create_index(
        "ix_telegram_message_map_hex", "telegram_message_map", ["hex"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_message_map_hex", table_name="telegram_message_map"
    )
    op.drop_index(
        "ix_telegram_message_map_message_id", table_name="telegram_message_map"
    )
    op.drop_index(
        "ix_telegram_message_map_chat_id", table_name="telegram_message_map"
    )
    op.drop_table("telegram_message_map")
