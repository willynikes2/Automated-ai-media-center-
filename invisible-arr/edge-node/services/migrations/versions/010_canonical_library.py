"""Add canonical library tables and user quota columns.

Revision ID: 010_canonical_library
Revises: 009_add_content_library
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "010_canonical_library"
down_revision = "009_add_content_library"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "canonical_content",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tmdb_id", sa.Integer, nullable=False),
        sa.Column("media_type", sa.String(10), nullable=False),
        sa.Column("title", sa.String(500)),
        sa.Column("canonical_path", sa.Text, nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger),
        sa.Column("quality", sa.String(50)),
        sa.Column("codec", sa.String(20)),
        sa.Column("radarr_id", sa.Integer),
        sa.Column("sonarr_id", sa.Integer),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("gc_eligible_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("tmdb_id", "media_type", name="uq_canonical_tmdb"),
        sa.Index("ix_canonical_content_tmdb_id", "tmdb_id"),
    )

    op.create_table(
        "user_content",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("canonical_content_id", UUID(as_uuid=True), sa.ForeignKey("canonical_content.id"), nullable=False),
        sa.Column("symlink_path", sa.Text),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("jobs.id"), nullable=True),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("added_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("removed_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("user_id", "canonical_content_id", name="uq_user_canonical"),
        sa.Index("ix_user_content_user_id", "user_id"),
        sa.Index("ix_user_content_canonical_id", "canonical_content_id"),
    )

    op.add_column("users", sa.Column("movie_quota", sa.Integer, server_default="50"))
    op.add_column("users", sa.Column("movie_count", sa.Integer, server_default="0"))
    op.add_column("users", sa.Column("tv_quota", sa.Integer, server_default="25"))
    op.add_column("users", sa.Column("tv_count", sa.Integer, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "tv_count")
    op.drop_column("users", "tv_quota")
    op.drop_column("users", "movie_count")
    op.drop_column("users", "movie_quota")
    op.drop_table("user_content")
    op.drop_table("canonical_content")
