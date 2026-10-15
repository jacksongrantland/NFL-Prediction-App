"""Append-only prospective schedule, roster and availability observations."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "observation_batches",
        sa.Column("id", sa.Text, primary_key=True),
        sa.Column("season", sa.Integer, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("observed_at", sa.Text, nullable=False),
        sa.Column("recorded_at", sa.Text, nullable=False),
        sa.Column("payload_json", sa.Text, nullable=False),
    )
    op.create_index(
        "ix_observation_lookup", "observation_batches", ["season", "kind", "recorded_at"]
    )
    for operation in ("UPDATE", "DELETE"):
        op.execute(
            f"CREATE TRIGGER observations_no_{operation.lower()} BEFORE {operation} "
            "ON observation_batches BEGIN SELECT RAISE(ABORT, 'observations are immutable'); END"
        )


def downgrade() -> None:
    op.drop_table("observation_batches")
