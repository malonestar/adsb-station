"""watchlist.notify — gate per-entry notification dispatch.

`notify=True` keeps the historical behavior: matches trigger Telegram/Discord.
`notify=False` makes a watchlist entry "passive" — it still flags aircraft on
the watchlist tab and shows up in alert history, but no outbound push. Used
to opt out of the notification flood that high-volume kinds (operator, type)
would otherwise produce.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Default existing rows to True so back-compat is preserved — every entry
    # in the seeded watchlist (all hex-kind) keeps firing notifications.
    op.add_column(
        "watchlist",
        sa.Column("notify", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    # Drop the server_default so the application controls the value going forward
    # (kind-aware default in the POST endpoint).
    with op.batch_alter_table("watchlist") as batch:
        batch.alter_column("notify", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("watchlist") as batch:
        batch.drop_column("notify")
