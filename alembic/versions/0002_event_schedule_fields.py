"""event schedule fields

Revision ID: 0002
Revises: 0001

The columns an imported schedule fills in. They are NOT NULL without defaults,
which is safe because no environment has stored events yet. Batch mode lets
SQLite (the tests) rebuild the table; Postgres runs plain ALTER TABLE.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TEXT_COLUMNS = (
    ("source", 32),
    ("source_event_id", 64),
    ("league", 8),
    ("home_team", 100),
    ("away_team", 100),
    ("status", 16),
)


def upgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        for name, length in NEW_TEXT_COLUMNS:
            batch_op.add_column(sa.Column(name, sa.String(length=length), nullable=False))
        batch_op.add_column(sa.Column("networks", sa.JSON(), nullable=False))
        batch_op.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            )
        )
        batch_op.create_index("ix_events_league_starts_at", ["league", "starts_at"], unique=False)
        batch_op.create_unique_constraint("uq_events_source_event", ["source", "source_event_id"])


def downgrade() -> None:
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_constraint("uq_events_source_event", type_="unique")
        batch_op.drop_index("ix_events_league_starts_at")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("networks")
        for name, _ in reversed(NEW_TEXT_COLUMNS):
            batch_op.drop_column(name)
