"""Add QA swarm tables."""
revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


def upgrade() -> None:
    op.create_table(
        "qa_runs",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("triggered_by", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("total_scenarios", sa.Integer, server_default="0"),
        sa.Column("passed", sa.Integer, server_default="0"),
        sa.Column("failed", sa.Integer, server_default="0"),
        sa.Column("errored", sa.Integer, server_default="0"),
        sa.Column("summary", sa.Text),
        sa.Column("test_user_email", sa.String(255)),
    )

    op.create_table(
        "qa_results",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID, sa.ForeignKey("qa_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("persona", sa.String(50), nullable=False),
        sa.Column("scenario_name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("error_message", sa.Text),
        sa.Column("error_fingerprint", sa.String(64)),
        sa.Column("correlation_ids", JSONB, server_default="[]"),
        sa.Column("screenshots", JSONB, server_default="[]"),
        sa.Column("github_issue_url", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_qa_results_run_id", "qa_results", ["run_id"])
    op.create_index("idx_qa_results_fingerprint", "qa_results", ["error_fingerprint"])

    op.create_table(
        "metrics_snapshots",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("overall_status", sa.String(20), nullable=False),
    )
    op.create_index("idx_metrics_snapshots_at", "metrics_snapshots", ["snapshot_at"])


def downgrade() -> None:
    op.drop_table("qa_results")
    op.drop_table("qa_runs")
    op.drop_table("metrics_snapshots")
