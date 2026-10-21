"""Paper-only accounts, manually entered lines, entries and append-only ledger."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    schemas = {
        "paper_accounts": [
            sa.Column("id", sa.Text, primary_key=True),
            sa.Column("created_at", sa.Text, nullable=False),
        ],
        "paper_lines": [
            sa.Column("id", sa.Text, primary_key=True),
            sa.Column("game_id", sa.Text, nullable=False),
            sa.Column("entered_at", sa.Text, nullable=False),
            sa.Column("payload_json", sa.Text, nullable=False),
        ],
        "paper_entries": [
            sa.Column("id", sa.Text, primary_key=True),
            sa.Column("account_id", sa.Text, sa.ForeignKey("paper_accounts.id"), nullable=False),
            sa.Column(
                "forecast_id", sa.Text, sa.ForeignKey("forecast_versions.id"), nullable=False
            ),
            sa.Column("line_id", sa.Text, sa.ForeignKey("paper_lines.id"), nullable=False),
            sa.Column("stake_minor", sa.Integer, nullable=False),
            sa.Column("created_at", sa.Text, nullable=False),
            sa.Column("idempotency_key", sa.Text, nullable=False),
            sa.UniqueConstraint("account_id", "idempotency_key"),
            sa.CheckConstraint("stake_minor > 0"),
        ],
        "paper_ledger": [
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("account_id", sa.Text, sa.ForeignKey("paper_accounts.id"), nullable=False),
            sa.Column("entry_id", sa.Text, sa.ForeignKey("paper_entries.id")),
            sa.Column("created_at", sa.Text, nullable=False),
            sa.Column("kind", sa.Text, nullable=False),
            sa.Column("amount_minor", sa.Integer, nullable=False),
            sa.Column("evidence_id", sa.Text),
        ],
        "paper_settlements": [
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("entry_id", sa.Text, sa.ForeignKey("paper_entries.id"), nullable=False),
            sa.Column("evidence_id", sa.Text, nullable=False),
            sa.Column("outcome", sa.Text, nullable=False),
            sa.Column("return_minor", sa.Integer, nullable=False),
            sa.Column("created_at", sa.Text, nullable=False),
            sa.UniqueConstraint("entry_id", "evidence_id"),
        ],
    }
    for name, columns in schemas.items():
        op.create_table(name, *columns)
        for operation in ("UPDATE", "DELETE"):
            op.execute(
                f"CREATE TRIGGER {name}_no_{operation.lower()} BEFORE {operation} ON {name} "
                "BEGIN SELECT RAISE(ABORT, 'paper history is immutable'); END"
            )
    op.create_index("ix_paper_ledger_account", "paper_ledger", ["account_id", "id"])


def downgrade():
    for name in (
        "paper_settlements",
        "paper_ledger",
        "paper_entries",
        "paper_lines",
        "paper_accounts",
    ):
        op.drop_table(name)
