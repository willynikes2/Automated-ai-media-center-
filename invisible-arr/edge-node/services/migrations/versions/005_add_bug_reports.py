"""Add bug_reports table.

Revision ID: 005
Revises: 004
Create Date: 2026-03-03 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bug_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("route", sa.String(500), nullable=False),
        sa.Column("description", sa.String(5000), nullable=False),
        sa.Column("correlation_id", sa.String(255), nullable=True),
        sa.Column("browser_info", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("admin_notes", sa.String(5000), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bug_reports_user_id", "bug_reports", ["user_id"])
    op.create_index("ix_bug_reports_status", "bug_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_bug_reports_status", table_name="bug_reports")
    op.drop_index("ix_bug_reports_user_id", table_name="bug_reports")
    op.drop_table("bug_reports")
