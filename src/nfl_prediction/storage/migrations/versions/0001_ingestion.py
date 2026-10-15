"""Initial ingestion metadata; no forecast/ledger tables before their stages."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("started_at", sa.Text, nullable=False),
        sa.Column("finished_at", sa.Text),
        sa.Column("error", sa.Text),
        sa.Column("report_json", sa.Text),
    )
    op.create_table(
        "download_cache",
        sa.Column("url", sa.Text, primary_key=True),
        sa.Column("metadata_json", sa.Text, nullable=False),
    )
    op.create_table(
        "source_manifests",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("manifest_json", sa.Text, nullable=False),
        sa.Column("raw_path", sa.Text, nullable=False),
    )
    op.create_table(
        "snapshots",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("season", sa.Integer, nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("summary_json", sa.Text, nullable=False),
    )
    op.create_table(
        "active_seasons",
        sa.Column("season", sa.Integer, primary_key=True),
        sa.Column("snapshot_id", sa.Text, sa.ForeignKey("snapshots.id"), nullable=False),
    )


def downgrade() -> None:
    for table in (
        "active_seasons",
        "snapshots",
        "source_manifests",
        "download_cache",
        "ingestion_runs",
    ):
        op.drop_table(table)
