"""stream recording

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("streams", sa.Column("hls_path", sa.String(length=22), nullable=True))
    op.add_column("streams", sa.Column("recording_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("streams", "recording_id")
    op.drop_column("streams", "hls_path")
