"""Add Google/Apple social auth fields to users.

Revision ID: 007
Revises: 006
Create Date: 2026-03-05 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_id", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("apple_id", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.String(2000), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "apple_id")
    op.drop_column("users", "google_id")
