"""create streams

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IS_LIVE = sa.text("ended_at IS NULL")


def upgrade() -> None:
    op.create_table(
        "streams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("commentator_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["commentator_id"],
            ["commentators.id"],
            name=op.f("fk_streams_commentator_id_commentators"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.id"],
            name=op.f("fk_streams_event_id_events"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_streams")),
    )
    op.create_index(
        "uq_streams_live_commentator",
        "streams",
        ["commentator_id"],
        unique=True,
        postgresql_where=IS_LIVE,
        sqlite_where=IS_LIVE,
    )
    op.create_index("ix_streams_event_id_started_at", "streams", ["event_id", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_streams_event_id_started_at", table_name="streams")
    op.drop_index("uq_streams_live_commentator", table_name="streams")
    op.drop_table("streams")
