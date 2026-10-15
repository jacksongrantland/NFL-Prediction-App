"""SQLite owns publication pointers and run history, not analytical rows."""

import json
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, text


class Database:
    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{(root / 'metadata.sqlite').as_posix()}")

        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=30000")
            connection.execute("PRAGMA journal_mode=WAL")

        config = Config()
        config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    def execute(self, sql: str, parameters: dict | None = None) -> None:
        with self.engine.begin() as connection:
            connection.execute(text(sql), parameters or {})

    def one(self, sql: str, parameters: dict | None = None) -> dict | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(sql), parameters or {}).mappings().first()
            return dict(row) if row else None

    def publish(self, snapshots: list[dict], run_id: str, report: dict) -> None:
        # One SQLite transaction changes every requested season together. A reader
        # sees the old publication or the complete new publication, never half a run.
        with self.engine.begin() as connection:
            for snapshot in snapshots:
                connection.execute(
                    text(
                        "INSERT OR IGNORE INTO snapshots(id, season, path, summary_json) "
                        "VALUES (:id, :season, :path, :summary_json)"
                    ),
                    {**snapshot, "summary_json": json.dumps(snapshot["summary"])},
                )
                connection.execute(
                    text(
                        "INSERT INTO active_seasons(season, snapshot_id) VALUES (:season, :id) "
                        "ON CONFLICT(season) DO UPDATE SET snapshot_id=excluded.snapshot_id"
                    ),
                    snapshot,
                )
            connection.execute(
                text(
                    "UPDATE ingestion_runs SET status='succeeded', finished_at=:finished, "
                    "report_json=:report WHERE id=:id"
                ),
                {"id": run_id, "finished": report["finished_at"], "report": json.dumps(report)},
            )

    def close(self) -> None:
        self.engine.dispose()
