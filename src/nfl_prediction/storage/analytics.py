"""Ephemeral DuckDB queries over immutable, SQLite-selected Parquet snapshots."""

from pathlib import Path

import duckdb

from nfl_prediction.data.ingest import verify_snapshot
from nfl_prediction.storage.database import Database

DATASETS = {"games", "plays", "player_stats", "team_stats", "rosters", "weekly_rosters"}


def season_counts(root: Path, season: int) -> dict[str, int]:
    db = Database(root.resolve())
    try:
        row = db.one(
            "SELECT s.path FROM snapshots s JOIN active_seasons a "
            "ON s.id=a.snapshot_id WHERE a.season=:season",
            {"season": season},
        )
        if row is None:
            raise ValueError(f"No published snapshot for season {season}")
        path = Path(row["path"])
        verify_snapshot(path)
        with duckdb.connect(":memory:") as connection:
            return {
                name: connection.execute(
                    "SELECT count(*) FROM read_parquet(?)", [str(path / f"{name}.parquet")]
                ).fetchone()[0]
                for name in sorted(DATASETS)
            }
    finally:
        db.close()
