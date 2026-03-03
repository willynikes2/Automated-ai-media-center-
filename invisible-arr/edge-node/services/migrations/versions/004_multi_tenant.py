"""Add multi-tenant user columns and invites table.

Revision ID: 004
Revises: 003
Create Date: 2026-03-03 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- New columns on users table ---
    op.add_column(
        "users",
        sa.Column("email", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=20), nullable=False, server_default=sa.text("'user'")),
    )
    op.add_column(
        "users",
        sa.Column("tier", sa.String(length=20), nullable=False, server_default=sa.text("'starter'")),
    )
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "users",
        sa.Column("storage_quota_gb", sa.Float(), nullable=False, server_default=sa.text("100.0")),
    )
    op.add_column(
        "users",
        sa.Column("storage_used_gb", sa.Float(), nullable=False, server_default=sa.text("0.0")),
    )
    op.add_column(
        "users",
        sa.Column("rd_api_token_enc", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("usenet_config_enc", sa.String(length=2000), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("jellyfin_user_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("jellyfin_token", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("max_concurrent_jobs", sa.Integer(), nullable=False, server_default=sa.text("2")),
    )
    op.add_column(
        "users",
        sa.Column("max_requests_per_day", sa.Integer(), nullable=False, server_default=sa.text("10")),
    )
    op.add_column(
        "users",
        sa.Column("requests_today", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "users",
        sa.Column("requests_reset_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("last_login", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "invited_by",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )

    # --- Create invites table ---
    op.create_table(
        "invites",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(length=50), unique=True, nullable=False),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("tier", sa.String(length=20), nullable=False, server_default=sa.text("'starter'")),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("times_used", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # --- Data migration: promote existing known users to admin/power ---
    op.execute(
        "UPDATE users SET role = 'admin', tier = 'power' WHERE name IN ('willynikes', 'default')"
    )


def downgrade() -> None:
    # --- Drop invites table ---
    op.drop_table("invites")

    # --- Drop new user columns (reverse order) ---
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_column("users", "invited_by")
    op.drop_column("users", "last_login")
    op.drop_column("users", "requests_reset_at")
    op.drop_column("users", "requests_today")
    op.drop_column("users", "max_requests_per_day")
    op.drop_column("users", "max_concurrent_jobs")
    op.drop_column("users", "jellyfin_token")
    op.drop_column("users", "jellyfin_user_id")
    op.drop_column("users", "usenet_config_enc")
    op.drop_column("users", "rd_api_token_enc")
    op.drop_column("users", "storage_used_gb")
    op.drop_column("users", "storage_quota_gb")
    op.drop_column("users", "is_active")
    op.drop_column("users", "tier")
    op.drop_column("users", "role")
    op.drop_column("users", "password_hash")
    op.drop_column("users", "email")
