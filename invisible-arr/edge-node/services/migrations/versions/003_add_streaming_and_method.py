"""Add streaming_urls and acquisition_method to jobs.

Revision ID: 003
Revises: 002
Create Date: 2026-03-03 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("streaming_urls", sa.JSON(), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("acquisition_method", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "acquisition_method")
    op.drop_column("jobs", "streaming_urls")
