"""Append-only local forecast audit; time is captured by the writer, never the caller payload."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import text

from nfl_prediction.data.ingest import json_hash
from nfl_prediction.storage.database import Database


def timestamp(value) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone-aware timestamp required")
    return parsed.astimezone(UTC)


def utc(value) -> str:
    return timestamp(value).isoformat()


class ForecastStore:
    def __init__(self, root: Path, clock=None):
        self.db = Database(root.resolve())
        self.clock = clock or (lambda: datetime.now(UTC))

    def close(self):
        self.db.close()

    def schedule(self, game_id: str, kickoff) -> None:
        now, kickoff = utc(self.clock()), utc(kickoff)
        latest = self.db.one(
            "SELECT * FROM forecast_schedule WHERE game_id=:game ORDER BY id DESC LIMIT 1",
            {"game": game_id},
        )
        if latest and latest["kickoff_at"] == kickoff:
            return
        self.db.execute(
            "INSERT INTO forecast_schedule(game_id, observed_at, kickoff_at) "
            "VALUES (:game,:now,:kickoff)",
            {"game": game_id, "now": now, "kickoff": kickoff},
        )

    def publish(self, payload: dict, *, retrospective: bool = False) -> str:
        required = {
            "game_id",
            "cutoff",
            "kickoff_at",
            "source_snapshots",
            "input_freshness",
            "model_versions",
            "simulation_seed",
            "simulation_config",
            "supported_outputs",
            "summary",
        }
        if not required <= payload.keys():
            raise ValueError(f"Missing forecast metadata: {sorted(required - payload.keys())}")
        if "generated_at" in payload:
            raise ValueError("Generation time is assigned by the writer; backdating rejected")
        now = timestamp(self.clock())
        cutoff, kickoff = timestamp(payload["cutoff"]), timestamp(payload["kickoff_at"])
        if cutoff > now or cutoff >= kickoff:
            raise ValueError(
                "Input cutoff must be no later than generation and earlier than kickoff"
            )
        if not retrospective and (
            now >= kickoff
            or self.db.one(
                "SELECT * FROM forecast_locks WHERE game_id=:game", {"game": payload["game_id"]}
            )
        ):
            raise ValueError("Live forecast is late or already locked")
        if not retrospective:
            with self.db.engine.connect() as connection:
                observations = (
                    connection.execute(
                        text("SELECT * FROM forecast_schedule WHERE game_id=:game ORDER BY id"),
                        {"game": payload["game_id"]},
                    )
                    .mappings()
                    .all()
                )
            if observations:
                previous = timestamp(observations[-1]["kickoff_at"])
                barrier = previous
                for old, updated in zip(observations, observations[1:]):
                    if timestamp(updated["observed_at"]) >= timestamp(old["kickoff_at"]):
                        barrier = min(barrier, timestamp(old["kickoff_at"]))
                if now >= barrier:
                    raise ValueError(
                        "Previously observed kickoff passed; cannot reopen live forecasts"
                    )
            self.schedule(payload["game_id"], kickoff)
        kind = "retrospective" if retrospective else "published_pregame"
        record = {**payload, "generated_at": utc(now), "kind": kind}
        identity = json_hash(record)
        with self.db.engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num=version_num"))
            if (
                not retrospective
                and connection.execute(
                    text("SELECT 1 FROM forecast_locks WHERE game_id=:game"),
                    {"game": payload["game_id"]},
                ).first()
            ):
                raise ValueError("Game became locked during publication")
            if not retrospective and timestamp(self.clock()) >= kickoff:
                raise ValueError("Kickoff passed during publication")
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO forecast_versions "
                    "VALUES (:id,:game,:generated,:kind,:payload)"
                ),
                {
                    "id": identity,
                    "game": payload["game_id"],
                    "generated": utc(now),
                    "kind": kind,
                    "payload": json.dumps(record, allow_nan=False),
                },
            )
        return identity

    def lock(self, game_id: str, *, minutes_before: int = 5) -> dict:
        if minutes_before < 0:
            raise ValueError("Lock offset must be nonnegative")
        now = timestamp(self.clock())
        with self.db.engine.begin() as connection:
            # Serialize selection and insertion across simultaneous jobs.
            connection.execute(text("UPDATE alembic_version SET version_num=version_num"))
            existing = (
                connection.execute(
                    text("SELECT * FROM forecast_locks WHERE game_id=:game"), {"game": game_id}
                )
                .mappings()
                .first()
            )
            if existing:
                return dict(existing)
            schedules = (
                connection.execute(
                    text("SELECT * FROM forecast_schedule WHERE game_id=:game ORDER BY id"),
                    {"game": game_id},
                )
                .mappings()
                .all()
            )
            if not schedules:
                raise ValueError("No observed schedule")
            kickoff = timestamp(schedules[-1]["kickoff_at"])
            # A schedule change observed after its previous kickoff never reopens it.
            for previous, updated in zip(schedules, schedules[1:]):
                if timestamp(updated["observed_at"]) >= timestamp(previous["kickoff_at"]):
                    kickoff = min(kickoff, timestamp(previous["kickoff_at"]))
            lock_at = kickoff - timedelta(minutes=minutes_before)
            if now < lock_at:
                raise ValueError("Lock time has not arrived")
            versions = (
                connection.execute(
                    text(
                        "SELECT * FROM forecast_versions WHERE game_id=:game "
                        "AND kind='published_pregame' ORDER BY generated_at DESC, id DESC"
                    ),
                    {"game": game_id},
                )
                .mappings()
                .all()
            )
            chosen = None
            for version in versions:
                payload = json.loads(version["payload_json"])
                if (
                    timestamp(version["generated_at"]) <= lock_at
                    and timestamp(payload["cutoff"]) <= lock_at
                    and timestamp(payload["kickoff_at"]) == kickoff
                ):
                    chosen = version["id"]
                    break
            record = {
                "game_id": game_id,
                "forecast_id": chosen,
                "locked_at": utc(now),
                "reason": "eligible_pregame" if chosen else "no_eligible_forecast",
                "kickoff_at": utc(kickoff),
                "lock_cutoff": utc(lock_at),
                "schedule_policy": "Never reopen after a previously observed kickoff",
            }
            connection.execute(
                text("INSERT INTO forecast_locks VALUES (:game,:forecast,:now,:payload)"),
                {
                    "game": game_id,
                    "forecast": chosen,
                    "now": utc(now),
                    "payload": json.dumps(record),
                },
            )
            return record

    def result(self, game_id: str, actual: dict, *, status: str, source_revision: str) -> str:
        if status not in ("provisional", "settled", "cancelled"):
            raise ValueError("Unknown result status")
        if status != "cancelled":
            for side in ("home", "away"):
                value = actual.get(f"{side}_score")
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError("Result scores must be nonnegative integers")
        record = {
            "game_id": game_id,
            "actual": actual,
            "status": status,
            "source_revision": source_revision,
        }
        identity = json_hash(record)
        self.db.execute(
            "INSERT OR IGNORE INTO result_revisions VALUES (:id,:game,:now,:payload)",
            {
                "id": identity,
                "game": game_id,
                "now": utc(self.clock()),
                "payload": json.dumps(record, allow_nan=False),
            },
        )
        return identity

    def audit(self, game_id: str) -> dict:
        params = {"game": game_id}
        with self.db.engine.connect() as connection:

            def rows(table, order):
                return [
                    dict(row)
                    for row in connection.execute(
                        text(f"SELECT * FROM {table} WHERE game_id=:game ORDER BY {order}"), params
                    ).mappings()
                ]

            forecasts = rows("forecast_versions", "generated_at, id")
            locks = rows("forecast_locks", "locked_at")
            results = rows("result_revisions", "recorded_at, rowid")
            schedule = rows("forecast_schedule", "id")
        errors = []
        if locks and locks[0]["forecast_id"]:
            version = next(f for f in forecasts if f["id"] == locks[0]["forecast_id"])
            summary = json.loads(version["payload_json"])["summary"]
            for revision in results:
                actual = json.loads(revision["payload_json"])
                if actual["status"] == "cancelled":
                    continue
                errors.append(
                    {
                        "forecast_id": version["id"],
                        "result_revision_id": revision["id"],
                        "status": actual["status"],
                        "home_error": summary["home_expected"] - actual["actual"]["home_score"],
                        "away_error": summary["away_expected"] - actual["actual"]["away_score"],
                        "player_errors": self._player_errors(summary, actual["actual"]),
                    }
                )
        return {
            "game_id": game_id,
            "forecasts": forecasts,
            "locks": locks,
            "results": results,
            "schedule": schedule,
            "errors": errors,
        }

    @staticmethod
    def _player_errors(summary, actual):
        errors = []
        observed = {(p["team_id"], p["player_id"]): p for p in actual.get("players", [])}
        for player in summary.get("player_summaries", []):
            row = observed.get((player["team_id"], player["player_id"]))
            if row is None:
                continue
            for stat, prediction in player["stats"].items():
                if row.get(stat) is not None:
                    errors.append(
                        {
                            "team_id": player["team_id"],
                            "player_id": player["player_id"],
                            "stat": stat,
                            "error": prediction["mean"] - row[stat],
                        }
                    )
        return errors


def reconcile(root: Path, season: int, clock=None) -> dict:
    """Append canonical normalized result revisions; missing player stats stay null."""
    from nfl_prediction.features.pipeline import load_history

    history, lineage = load_history(root, [season])
    store = ForecastStore(root, clock=clock)
    count = 0
    try:
        games = history["games"]
        for game in games.loc[games.result_status.eq("final")].to_dict("records"):
            rows = history["player_stats"].loc[history["player_stats"].game_id.eq(game["game_id"])]
            actual = {
                "home_score": int(game["home_score"]),
                "away_score": int(game["away_score"]),
                "players": json.loads(rows.to_json(orient="records")),
            }
            store.result(
                game["game_id"], actual, status="settled", source_revision=lineage[str(season)]
            )
            count += 1
        return {"season": season, "completed_games_reconciled": count, "source_snapshots": lineage}
    finally:
        store.close()
