"""Add Sonarr/Radarr integration fields to jobs and users.

Revision ID: 006
Revises: 005
Create Date: 2026-03-04 08:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Job table — Sonarr/Radarr tracking fields
    op.add_column("jobs", sa.Column("sonarr_series_id", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("radarr_movie_id", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("arr_queue_id", sa.Integer(), nullable=True))

    # User table — per-user root folder IDs
    op.add_column("users", sa.Column("radarr_root_folder_id", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("sonarr_root_folder_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "sonarr_root_folder_id")
    op.drop_column("users", "radarr_root_folder_id")
    op.drop_column("jobs", "arr_queue_id")
    op.drop_column("jobs", "radarr_movie_id")
    op.drop_column("jobs", "sonarr_series_id")
