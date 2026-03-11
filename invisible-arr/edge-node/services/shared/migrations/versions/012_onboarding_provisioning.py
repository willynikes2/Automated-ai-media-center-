"""Add onboarding provisioning columns and rd_pool_accounts table.

Revision ID: 012
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "012"
down_revision = "008"


def upgrade() -> None:
    op.add_column("users", sa.Column("iptv_line_username", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("iptv_line_password_enc", sa.String(1000), nullable=True))
    op.add_column("users", sa.Column("iptv_provisioned_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("rd_source", sa.String(20), server_default="user_provided", nullable=False))
    op.add_column("users", sa.Column("rd_pool_account_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("onboarding_status", JSONB(), nullable=True))

    op.create_table(
        "rd_pool_accounts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("api_token_enc", sa.String(1000), nullable=False),
        sa.Column("max_users", sa.Integer(), server_default="5", nullable=False),
        sa.Column("current_users", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_foreign_key(
        "fk_users_rd_pool_account", "users", "rd_pool_accounts",
        ["rd_pool_account_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_rd_pool_account", "users", type_="foreignkey")
    op.drop_table("rd_pool_accounts")
    op.drop_column("users", "onboarding_status")
    op.drop_column("users", "rd_pool_account_id")
    op.drop_column("users", "rd_source")
    op.drop_column("users", "iptv_provisioned_at")
    op.drop_column("users", "iptv_line_password_enc")
    op.drop_column("users", "iptv_line_username")
