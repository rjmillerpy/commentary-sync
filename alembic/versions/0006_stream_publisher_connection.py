"""stream publisher connection

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("streams", sa.Column("publisher_sid", sa.String(length=64), nullable=True))
    op.add_column(
        "streams", sa.Column("publisher_left_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("streams", "publisher_left_at")
    op.drop_column("streams", "publisher_sid")
