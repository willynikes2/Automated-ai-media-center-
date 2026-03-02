"""Initial schema — all 7 tables.

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ──
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("api_key", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_key"),
    )

    # ── prefs ──
    op.create_table(
        "prefs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("max_resolution", sa.Integer(), nullable=False, server_default="1080"),
        sa.Column("allow_4k", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "max_movie_size_gb",
            sa.Float(),
            nullable=False,
            server_default="15.0",
        ),
        sa.Column(
            "max_episode_size_gb",
            sa.Float(),
            nullable=False,
            server_default="4.0",
        ),
        sa.Column("prune_watched_after_days", sa.Integer(), nullable=True),
        sa.Column("keep_favorites", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "storage_soft_limit_percent",
            sa.Integer(),
            nullable=False,
            server_default="90",
        ),
        sa.Column(
            "upgrade_policy",
            sa.String(length=20),
            nullable=False,
            server_default="off",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── jobs ──
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("media_type", sa.String(length=10), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("query", sa.String(length=500), nullable=True),
        sa.Column("season", sa.Integer(), nullable=True),
        sa.Column("episode", sa.Integer(), nullable=True),
        sa.Column(
            "state",
            sa.String(length=50),
            nullable=False,
            server_default="CREATED",
        ),
        sa.Column("selected_candidate", sa.JSON(), nullable=True),
        sa.Column("rd_torrent_id", sa.String(length=255), nullable=True),
        sa.Column("imported_path", sa.String(length=1000), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── job_events ──
    op.create_table(
        "job_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("message", sa.String(length=2000), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── blacklists ──
    op.create_table(
        "blacklists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("release_hash", sa.String(length=255), nullable=False),
        sa.Column("release_title", sa.String(length=1000), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── iptv_sources ──
    op.create_table(
        "iptv_sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("m3u_url", sa.String(length=2000), nullable=False),
        sa.Column("epg_url", sa.String(length=2000), nullable=True),
        sa.Column(
            "source_timezone",
            sa.String(length=100),
            nullable=False,
            server_default="UTC",
        ),
        sa.Column("headers_json", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── iptv_channels ──
    op.create_table(
        "iptv_channels",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("tvg_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("group_title", sa.String(length=500), nullable=True),
        sa.Column("logo", sa.String(length=2000), nullable=True),
        sa.Column("stream_url", sa.String(length=2000), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("channel_number", sa.Integer(), nullable=True),
        sa.Column("preferred_name", sa.String(length=500), nullable=True),
        sa.Column("preferred_group", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["iptv_sources.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("iptv_channels")
    op.drop_table("iptv_sources")
    op.drop_table("blacklists")
    op.drop_table("job_events")
    op.drop_table("jobs")
    op.drop_table("prefs")
    op.drop_table("users")
