"""Immutable pregame versions, locks, schedule observations and result revisions."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    for table, columns in {
        "forecast_versions": [
            sa.Column("id", sa.Text, primary_key=True),
            sa.Column("game_id", sa.Text, nullable=False),
            sa.Column("generated_at", sa.Text, nullable=False),
            sa.Column("kind", sa.Text, nullable=False),
            sa.Column("payload_json", sa.Text, nullable=False),
        ],
        "forecast_locks": [
            sa.Column("game_id", sa.Text, primary_key=True),
            sa.Column("forecast_id", sa.Text, sa.ForeignKey("forecast_versions.id")),
            sa.Column("locked_at", sa.Text, nullable=False),
            sa.Column("payload_json", sa.Text, nullable=False),
        ],
        "forecast_schedule": [
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("game_id", sa.Text, nullable=False),
            sa.Column("observed_at", sa.Text, nullable=False),
            sa.Column("kickoff_at", sa.Text, nullable=False),
        ],
        "result_revisions": [
            sa.Column("id", sa.Text, primary_key=True),
            sa.Column("game_id", sa.Text, nullable=False),
            sa.Column("recorded_at", sa.Text, nullable=False),
            sa.Column("payload_json", sa.Text, nullable=False),
        ],
    }.items():
        op.create_table(table, *columns)
        op.create_index(f"ix_{table}_game", table, ["game_id"])
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} "
                f"ON {table} BEGIN SELECT RAISE(ABORT, 'history is immutable'); END"
            )


def downgrade():
    for table in ("result_revisions", "forecast_schedule", "forecast_locks", "forecast_versions"):
        op.drop_table(table)
