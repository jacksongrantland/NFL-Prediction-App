"""Prospective observations, conservative as-of queries and manual availability input."""

import csv
import hashlib
import io
import json
import re
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from nfl_prediction.data.downloads import Downloader, file_hash
from nfl_prediction.data.ingest import RELEASE, SOURCES, ingestion_lock, json_hash, save_manifest
from nfl_prediction.data.normalize import (
    GAME_TYPES,
    TEAM_ALIASES,
    TEAM_CODES,
    normalize,
    read_source,
)
from nfl_prediction.storage.database import Database

INJURIES_URL = RELEASE + "injuries/injuries_{season}.parquet"
STATUS_FIELDS = ("injury_designation", "practice_participation", "roster_status", "game_inactive")
MANUAL_COLUMNS = (
    "player_id",
    "game_id",
    "team_id",
    "source_url",
    "published_at",
    "observed_at",
    *STATUS_FIELDS,
)


def timestamp(value: str | datetime) -> datetime:
    parsed = (
        datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamps must include a timezone")
    return parsed.astimezone(UTC)


def iso(value: str | datetime) -> str:
    return timestamp(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def records(frame: pd.DataFrame) -> list[dict]:
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def save_batches(db: Database, batches: list[dict], recorded_at: datetime) -> list[str]:
    """Validate before entry; publish all prepared observations in one transaction."""
    identities = []
    with db.engine.begin() as connection:
        for batch in batches:
            value = {**batch, "recorded_at": iso(recorded_at), "schema_version": "observations/1"}
            identity = json_hash(value)
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO observation_batches "
                    "(id, season, kind, source, observed_at, recorded_at, payload_json) "
                    "VALUES (:id, :season, :kind, :source, :observed_at, :recorded_at, :payload)"
                ),
                {**value, "id": identity, "payload": json.dumps(value)},
            )
            identities.append(identity)
    return identities


def injury_rows(raw: pd.DataFrame, games: pd.DataFrame, season: int) -> tuple[list, list]:
    required = {
        "season",
        "week",
        "game_type",
        "team",
        "gsis_id",
        "report_status",
        "practice_status",
    }
    if not required.issubset(raw.columns):
        raise ValueError(f"Injuries missing columns: {sorted(required - set(raw.columns))}")
    accepted, rejected = [], []
    for number, row in enumerate(records(raw), 1):
        team = TEAM_ALIASES.get(row["team"], row["team"])
        game_type = GAME_TYPES.get(row["game_type"])
        candidates = games.loc[
            games.season.eq(row["season"])
            & games.week.eq(row["week"])
            & games.game_type.eq(game_type)
            & (games.home_team_id.eq(team) | games.away_team_id.eq(team))
        ]
        if (
            row["season"] != season
            or team not in TEAM_CODES
            or not re.fullmatch(r"\d{2}-\d{7}", row["gsis_id"] or "")
            or game_type is None
            or len(candidates) != 1
        ):
            rejected.append(
                {"source_row_number": number, "reason": "unresolved_identity_or_game", "raw": row}
            )
            continue
        accepted.append(
            {
                "source_row_number": number,
                "player_id": row["gsis_id"],
                "team_id": team,
                "game_id": candidates.iloc[0].game_id,
                "injury_designation": row["report_status"],
                "practice_participation": row["practice_status"],
                "roster_status": None,
                "game_inactive": None,
                "published_at": None,
                "source_modified_at": row.get("date_modified"),
                "injury_fields": {key: value for key, value in row.items() if "injury" in key},
            }
        )
    keys = [(row["game_id"], row["player_id"]) for row in accepted]
    if len(keys) != len(set(keys)):
        raise ValueError("Ambiguous duplicate injury observations for player/game")
    return accepted, rejected


def capture(
    season: int, root: Path, *, include_injuries: bool = True, downloader_factory=Downloader
) -> dict:
    """Revalidate current sources; never backdate observations to source game weeks."""
    root = root.resolve()
    with ingestion_lock(root):
        db = Database(root)
        try:
            downloader = downloader_factory(root, db)
            batches, frames = [], {}
            for kind, dataset in (("schedule", "games"), ("roster", "rosters")):
                source = downloader.fetch(SOURCES[dataset].format(season=season), refresh=True)
                raw, columns = read_source(Path(source.path), dataset)
                manifest_id = save_manifest(db, source, dataset, season, columns, root)
                frame, summary, rejected = normalize(raw, dataset, season, manifest_id)
                frames[kind] = frame
                batches.append(
                    {
                        "season": season,
                        "kind": kind,
                        "source": "nflverse",
                        "observed_at": iso(datetime.now(UTC)),
                        "source_metadata": asdict(source),
                        "source_manifest_id": manifest_id,
                        "rows": records(frame),
                        "rejected": records(rejected),
                        "summary": summary,
                        "status": "observed",
                        "published_at": None,
                    }
                )
            injury = {
                "season": season,
                "kind": "injury",
                "source": "nflverse",
                "rows": [],
                "rejected": [],
                "published_at": None,
            }
            if include_injuries:
                try:
                    source = downloader.fetch(INJURIES_URL.format(season=season), refresh=True)
                    raw = pd.read_parquet(source.path)
                    manifest_id = save_manifest(
                        db, source, "injuries", season, list(raw.columns), root
                    )
                    rows, rejected = injury_rows(raw, frames["schedule"], season)
                    injury.update(
                        rows=rows,
                        rejected=rejected,
                        status="observed",
                        source_metadata=asdict(source),
                        source_manifest_id=manifest_id,
                    )
                except (OSError, ValueError, RuntimeError) as error:
                    injury.update(status="unavailable", error=str(error))
            else:
                injury.update(status="disabled")
            injury["observed_at"] = iso(datetime.now(UTC))
            batches.append(injury)
            ids = save_batches(db, batches, datetime.now(UTC))
            return {
                "batch_ids": ids,
                "datasets": [
                    {
                        "kind": b["kind"],
                        "status": b["status"],
                        "rows": len(b["rows"]),
                        "rejected_rows": len(b["rejected"]),
                        "error": b.get("error"),
                    }
                    for b in batches
                ],
            }
        finally:
            db.close()


def eligible_batches(db: Database, season: int, cutoff: datetime) -> list[dict]:
    with db.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT id, payload_json FROM observation_batches "
                "WHERE season=:season AND recorded_at<=:cutoff AND observed_at<=:cutoff "
                "ORDER BY recorded_at, observed_at, id"
            ),
            {"season": season, "cutoff": iso(cutoff)},
        ).mappings()
        return [{**json.loads(row["payload_json"]), "batch_id": row["id"]} for row in rows]


def import_availability(path: Path, season: int, root: Path) -> dict:
    """Import explicit manual observations atomically; recorded time is always local now."""
    from pydantic import HttpUrl, TypeAdapter

    with ingestion_lock(root):
        db = Database(root.resolve())
        try:
            now = datetime.now(UTC)
            batches = eligible_batches(db, season, now)
            schedules = [b for b in batches if b["kind"] == "schedule"]
            if not schedules:
                raise ValueError("Capture a schedule snapshot before importing availability")
            games = {g["game_id"]: g for g in schedules[-1]["rows"]}
            prepared, seen = [], set()
            content = path.read_bytes()
            content_hash = hashlib.sha256(content).hexdigest()
            with io.StringIO(content.decode("utf-8-sig"), newline="") as stream:
                reader = csv.DictReader(stream)
                if set(reader.fieldnames or []) != set(MANUAL_COLUMNS) or len(
                    reader.fieldnames or []
                ) != len(MANUAL_COLUMNS):
                    raise ValueError(f"Manual CSV columns must be exactly {MANUAL_COLUMNS}")
                for number, raw in enumerate(reader, 1):
                    if None in raw or any(value is None for value in raw.values()):
                        raise ValueError(f"Malformed CSV row {number}")
                    row = {key: value.strip() or None for key, value in raw.items()}
                    if not re.fullmatch(r"\d{2}-\d{7}", row["player_id"] or ""):
                        raise ValueError(f"Invalid GSIS player_id on row {number}")
                    game = games.get(row["game_id"])
                    team = TEAM_ALIASES.get(row["team_id"], row["team_id"])
                    if game is None or team not in (game["home_team_id"], game["away_team_id"]):
                        raise ValueError(f"Unresolved game/team on row {number}")
                    row["team_id"] = team
                    row["source_url"] = str(TypeAdapter(HttpUrl).validate_python(row["source_url"]))
                    observed = timestamp(row["observed_at"] or "")
                    published = timestamp(row["published_at"]) if row["published_at"] else None
                    if observed > now or (published and published > observed):
                        raise ValueError("Require published_at <= observed_at <= local import time")
                    if row["game_inactive"] not in (None, "true", "false"):
                        raise ValueError("game_inactive must be true, false or blank")
                    row["game_inactive"] = {"true": True, "false": False, None: None}[
                        row["game_inactive"]
                    ]
                    if all(row[field] is None for field in STATUS_FIELDS):
                        raise ValueError("At least one structured status is required")
                    key = (row["player_id"], row["game_id"], iso(observed))
                    if key in seen:
                        raise ValueError("Duplicate player/game/observation in CSV")
                    seen.add(key)
                    row.update(
                        observed_at=iso(observed),
                        published_at=iso(published) if published else None,
                        source_row_number=number,
                    )
                    prepared.append(
                        {
                            "season": season,
                            "kind": "injury",
                            "source": "manual",
                            "observed_at": iso(observed),
                            "rows": [row],
                            "status": "observed",
                            "file_sha256": content_hash,
                            "rejected": [],
                        }
                    )
            if not prepared:
                raise ValueError("Manual CSV has no observations")
            raw_path = root.resolve() / "raw" / "manual" / f"{content_hash}.csv"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            if raw_path.exists():
                if file_hash(raw_path) != content_hash:
                    raise ValueError("Immutable manual import is corrupt")
            else:
                with raw_path.open("xb") as stream:
                    stream.write(content)
            for batch in prepared:
                batch["raw_path"] = str(raw_path)
            return {
                "batch_ids": save_batches(db, prepared, datetime.now(UTC)),
                "rows": len(prepared),
            }
        finally:
            db.close()


def as_of(
    season: int, game_id: str, cutoff: str | datetime, root: Path, *, stale_hours: float = 36
) -> dict:
    """Only local knowledge by cutoff is eligible, including manual report revisions."""
    cutoff = timestamp(cutoff)
    if stale_hours <= 0:
        raise ValueError("stale_hours must be positive")
    db = Database(root.resolve())
    try:
        batches = eligible_batches(db, season, cutoff)
    finally:
        db.close()
    latest = {b["kind"]: b for b in batches if b["source"] == "nflverse"}

    def freshness(batch: dict | None) -> str:
        if batch is None:
            return "missing"
        if batch["status"] != "observed":
            return batch["status"]
        return (
            "stale"
            if cutoff - timestamp(batch["observed_at"]) > timedelta(hours=stale_hours)
            else "observed"
        )

    schedule = latest.get("schedule")
    game = (
        next((g for g in schedule["rows"] if g["game_id"] == game_id), None) if schedule else None
    )
    roster = latest.get("roster")
    players = (
        [
            p
            for p in roster["rows"]
            if game and p["team_id"] in (game["home_team_id"], game["away_team_id"])
        ]
        if roster
        else []
    )
    injury_batch = latest.get("injury")
    candidates = ([injury_batch] if injury_batch else []) + [
        b for b in batches if b["source"] == "manual"
    ]
    states = {}
    for batch in sorted(
        candidates, key=lambda b: (b["observed_at"], b["recorded_at"], b["batch_id"])
    ):
        for row in batch["rows"]:
            if row["game_id"] == game_id:
                states[row["player_id"]] = {
                    **row,
                    "batch_id": batch["batch_id"],
                    "observed_at": batch["observed_at"],
                    "recorded_at": batch["recorded_at"],
                    "freshness": freshness(batch),
                    "source": batch["source"],
                    "source_url": row.get("source_url")
                    or batch.get("source_metadata", {}).get("url"),
                }
    for player in players:
        states.setdefault(
            player["player_id"],
            {
                "player_id": player["player_id"],
                "game_id": game_id,
                **dict.fromkeys(STATUS_FIELDS),
                "freshness": "unknown",
            },
        )
    return {
        "game_id": game_id,
        "cutoff": iso(cutoff),
        "game": game,
        "schedule_freshness": freshness(schedule),
        "schedule_batch_id": schedule["batch_id"] if schedule else None,
        "roster_freshness": freshness(roster),
        "roster_batch_id": roster["batch_id"] if roster else None,
        "injury_source_status": freshness(injury_batch),
        "injury_coverage": "unknown",
        "roster": players,
        "availability": sorted(states.values(), key=lambda r: r["player_id"]),
        "mode": "structured_availability"
        if any(s["freshness"] == "observed" for s in states.values())
        else "no_injury_data",
        "limitations": "Unknown is not healthy or inactive; no playing probabilities inferred.",
    }
