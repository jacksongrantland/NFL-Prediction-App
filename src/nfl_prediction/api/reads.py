"""Read-only repository for local dashboard requests; no migrations or model execution."""

import json
import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

import pandas as pd


@contextmanager
def connection(root: Path):
    path = (root / "metadata.sqlite").resolve()
    if not path.exists():
        yield None
        return
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def query(root: Path, sql: str, values=()) -> list[dict]:
    with connection(root) as db:
        if db is None:
            return []
        try:
            return [dict(row) for row in db.execute(sql, values).fetchall()]
        except sqlite3.OperationalError as error:
            if "no such table" in str(error):
                return []
            raise


def snapshot(root: Path, season: int):
    rows = query(
        root,
        "SELECT s.* FROM snapshots s JOIN active_seasons a ON a.snapshot_id=s.id WHERE a.season=?",
        (season,),
    )
    return rows[0] if rows else None


@lru_cache(maxsize=8)
def read_schedule(path: str, identity: str) -> list[dict]:
    frame = pd.read_parquet(Path(path) / "games.parquet")
    return json.loads(
        frame.sort_values(["kickoff_at", "game_id"]).to_json(orient="records", date_format="iso")
    )


@lru_cache(maxsize=8)
def names(path: str, identity: str) -> dict:
    frame = pd.read_parquet(Path(path) / "rosters.parquet")
    return {
        row.player_id: {
            "name": row.full_name if pd.notna(row.full_name) else row.player_id,
            "position": row.position,
        }
        for row in frame.dropna(subset=["player_id"]).itertuples()
    }


def games(root: Path, season: int) -> list[dict]:
    active = snapshot(root, season)
    if not active:
        return []
    rows = read_schedule(active["path"], active["id"])
    versions = query(
        root,
        "SELECT game_id, COUNT(*) AS n FROM forecast_versions "
        "WHERE kind='published_pregame' GROUP BY game_id",
    )
    counts = {v["game_id"]: v["n"] for v in versions}
    locked = {v["game_id"]: v["forecast_id"] for v in query(root, "SELECT * FROM forecast_locks")}
    return [
        {
            **r,
            "forecast_count": counts.get(r["game_id"], 0),
            "official_forecast_id": locked.get(r["game_id"]),
            "lock_status": "locked"
            if locked.get(r["game_id"])
            else "missing_forecast"
            if r["game_id"] in locked
            else "open",
        }
        for r in rows
    ]


def versions(root: Path, game_id: str, limit: int = 20, offset: int = 0) -> list[dict]:
    rows = query(
        root,
        "SELECT * FROM forecast_versions WHERE game_id=? "
        "ORDER BY generated_at DESC, id DESC LIMIT ? OFFSET ?",
        (game_id, limit, offset),
    )
    return [{"id": r["id"], **json.loads(r["payload_json"])} for r in rows]


def forecast(root: Path, identity: str):
    rows = query(root, "SELECT * FROM forecast_versions WHERE id=?", (identity,))
    return {"id": identity, **json.loads(rows[0]["payload_json"])} if rows else None


def actuals(root: Path, game_id: str):
    rows = query(
        root,
        "SELECT * FROM result_revisions WHERE game_id=? ORDER BY recorded_at DESC, rowid DESC",
        (game_id,),
    )
    return [
        {"id": r["id"], "recorded_at": r["recorded_at"], **json.loads(r["payload_json"])}
        for r in rows
    ]


def audit(root: Path, game_id: str):
    from nfl_prediction.storage.forecasts import ForecastStore

    forecasts, revisions = versions(root, game_id), actuals(root, game_id)
    locks = query(root, "SELECT * FROM forecast_locks WHERE game_id=?", (game_id,))
    official = (
        forecast(root, locks[0]["forecast_id"]) if locks and locks[0]["forecast_id"] else None
    )
    if official and all(version["id"] != official["id"] for version in forecasts):
        # Keep the authoritative version available even beyond the recent-version page.
        forecasts = [official, *forecasts]
    errors = []
    eligibility = "no_forecast"
    if official:
        from nfl_prediction.storage.forecasts import timestamp

        schedule = query(
            root,
            "SELECT kickoff_at FROM forecast_schedule WHERE game_id=? ORDER BY id DESC LIMIT 1",
            (game_id,),
        )
        eligibility = (
            "rescheduled_after_lock"
            if schedule
            and timestamp(schedule[0]["kickoff_at"]) != timestamp(official["kickoff_at"])
            else "eligible"
        )
        for revision in revisions if eligibility == "eligible" else []:
            if revision["status"] != "cancelled":
                errors.append(
                    {
                        "forecast_id": official["id"],
                        "result_revision_id": revision["id"],
                        "status": revision["status"],
                        "home_error": official["summary"]["home_expected"]
                        - revision["actual"]["home_score"],
                        "away_error": official["summary"]["away_expected"]
                        - revision["actual"]["away_score"],
                        "player_errors": ForecastStore._player_errors(
                            official["summary"], revision["actual"]
                        ),
                    }
                )
    return {
        "game_id": game_id,
        "versions": forecasts,
        "official_forecast_id": official["id"] if official else None,
        "locks": [json.loads(r["payload_json"]) for r in locks],
        "actuals": revisions,
        "errors": errors,
        "eligibility_status": eligibility,
    }
