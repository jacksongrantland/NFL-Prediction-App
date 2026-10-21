"""Repeatable ingestion with immutable snapshots and atomic SQLite publication."""

import hashlib
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pyarrow

from nfl_prediction.data.audit import SCHEDULE_URL, utc_now
from nfl_prediction.data.downloads import Download, Downloader, file_hash
from nfl_prediction.data.manifests import SourceManifest
from nfl_prediction.data.normalize import (
    NORMALIZER_VERSION,
    normalize,
    read_source,
    reconcile,
)
from nfl_prediction.storage.database import Database

RELEASE = "https://github.com/nflverse/nflverse-data/releases/download/"
SOURCES = {
    "games": SCHEDULE_URL,
    "rosters": RELEASE + "rosters/roster_{season}.parquet",
    "weekly_rosters": RELEASE + "weekly_rosters/roster_weekly_{season}.parquet",
    "player_stats": RELEASE + "stats_player/stats_player_week_{season}.parquet",
    "team_stats": RELEASE + "stats_team/stats_team_week_{season}.parquet",
    "plays": RELEASE + "pbp/play_by_play_{season}.parquet",
}


def json_hash(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@contextmanager
def ingestion_lock(root: Path, filename: str = "ingestion.lock"):
    """OS lock releases on process exit/crash; the harmless lock file may remain."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / filename).open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RuntimeError("Another ingestion is already running") from error
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def save_manifest(
    db: Database, source: Download, dataset: str, season: int, columns: list[str], root: Path
) -> str:
    updated = parsedate_to_datetime(source.last_modified) if source.last_modified else None
    manifest = SourceManifest(
        dataset=dataset,
        season=season,
        source_url=source.url,
        retrieved_at=source.retrieved_at,
        source_updated_at=updated,
        sha256=source.sha256,
        checksum_scope="full_artifact",
        byte_count=source.size,
        source_schema_version=json_hash({"columns": columns}),
        coverage="partial_season",
        attribution_url=(
            "https://github.com/nflverse/nfldata"
            if dataset == "games"
            else "https://github.com/nflverse/nflverse-data"
        ),
        redistribution_status="review_required",
    )
    value = manifest.model_dump(mode="json")
    identity = json_hash(value)
    folder = root / "raw" / "manifests"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{identity}.json"
    if not path.exists():
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    db.execute(
        "INSERT OR IGNORE INTO source_manifests(id, manifest_json, raw_path) "
        "VALUES (:id, :manifest, :path)",
        {"id": identity, "manifest": json.dumps(value), "path": source.path},
    )
    return identity


def verify_snapshot(path: Path) -> dict:
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    for name, checksum in summary["file_checksums"].items():
        file = path / name
        if not file.is_file() or file_hash(file) != checksum:
            raise ValueError(f"Normalized snapshot integrity failure: {file}")
    return summary


def build_snapshot(season: int, sources: dict[str, Download], root: Path, db: Database) -> dict:
    from nfl_prediction.data import normalize as normalizer_module

    schedule, _ = read_source(Path(sources["games"].path), "games")
    relevant_schedule = schedule.loc[schedule.season.astype("string").eq(str(season))]
    schedule_key = hashlib.sha256(
        relevant_schedule.drop(columns="source_row_number").to_json(orient="records").encode()
    ).hexdigest()
    fingerprint = {
        "season": season,
        "normalizer": NORMALIZER_VERSION,
        "normalizer_code_sha256": file_hash(Path(normalizer_module.__file__)),
        "pandas_version": pd.__version__,
        "pyarrow_version": pyarrow.__version__,
        "sources": {
            name: (schedule_key if name == "games" else source.sha256)
            for name, source in sorted(sources.items())
        },
        "schedule_key_scope": "requested_season_rows",
    }
    identity = json_hash(fingerprint)
    destination = root / "normalized" / str(season) / identity
    if destination.is_dir():
        summary = verify_snapshot(destination)
        return {
            "id": identity,
            "season": season,
            "path": str(destination),
            "summary": summary,
            "reused": True,
        }
    staging = root / "normalized" / f".staging-{uuid4().hex}"
    staging.mkdir(parents=True)
    frames, summaries, manifests, rejects = {}, {}, {}, {}
    baseline_path = Path(__file__).parents[3] / "docs" / "source_audit_2026-10-14.json"
    # Baseline comparison is diagnostic only; required columns are enforced in code.
    baseline = (
        json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else {}
    )
    family_names = {"games": "schedules", "plays": "pbp"}
    for dataset, source in sources.items():
        raw, columns = read_source(Path(source.path), dataset)
        manifest_id = save_manifest(db, source, dataset, season, columns, root)
        frames[dataset], summaries[dataset], rejects[dataset] = normalize(
            raw, dataset, season, manifest_id
        )
        manifests[dataset] = manifest_id
        prior = (
            baseline.get("schedules", {})
            if dataset == "games"
            else next(
                (
                    entry
                    for entry in baseline.get("datasets", [])
                    if entry["dataset"] == family_names.get(dataset, dataset)
                    and entry["season"] == season
                ),
                {},
            )
        )
        summaries[dataset]["schema_changes_from_audit"] = {
            "added": sorted(set(columns) - set(prior.get("columns", columns))),
            "removed": sorted(set(prior.get("columns", columns)) - set(columns)),
        }
    coverage = reconcile(frames)
    for dataset, frame in frames.items():
        frame.to_parquet(staging / f"{dataset}.parquet", index=False, compression="zstd")
        summaries[dataset]["published_rows"] = len(frame)
        if not rejects[dataset].empty:
            rejects[dataset].to_parquet(staging / f"{dataset}_rejected.parquet", index=False)
    player_teams = frames["player_stats"].groupby("player_id").team_id.nunique()
    summary = {
        "snapshot_id": identity,
        "season": season,
        "created_at": utc_now(),
        "fingerprint": fingerprint,
        "source_manifests": manifests,
        "datasets": summaries,
        "coverage": coverage,
        "players_with_multiple_game_teams": int(player_teams.gt(1).sum()),
        "historical_availability": "approximate_corrected_sources",
        "file_checksums": {path.name: file_hash(path) for path in staging.glob("*.parquet")},
    }
    (staging / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    verify_snapshot(staging)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging.rename(destination)
    return {
        "id": identity,
        "season": season,
        "path": str(destination),
        "summary": summary,
        "reused": False,
    }


def run_ingestion(
    seasons: list[int],
    root: Path,
    *,
    current_season: int,
    force_refresh: bool = False,
    downloader_factory=Downloader,
    progress=print,
) -> dict:
    root = root.resolve()
    with ingestion_lock(root):
        db = Database(root)
        run_id, started, timer = uuid4().hex, utc_now(), time.perf_counter()
        # A crashed process cannot still hold the OS lock. Preserve its run as interrupted.
        db.execute(
            "UPDATE ingestion_runs SET status='interrupted', finished_at=:now "
            "WHERE status='running'",
            {"now": started},
        )
        db.execute(
            "INSERT INTO ingestion_runs(id, status, started_at) VALUES (:id, 'running', :started)",
            {"id": run_id, "started": started},
        )
        snapshots, skipped = [], []
        try:
            downloader = downloader_factory(root, db)
            for season in sorted(set(seasons)):
                progress(f"Ingesting {season}: downloading or verifying six sources...")
                if season == current_season:
                    schedule_source = downloader.fetch(
                        SOURCES["games"], refresh=True, force=force_refresh
                    )
                    schedule, _ = read_source(Path(schedule_source.path), "games")
                    annual = schedule.loc[schedule.season.astype("string").eq(str(season))]
                    if annual.empty:
                        skipped.append({"season": season, "reason": "schedule_not_available"})
                        continue
                    games, _, _ = normalize(schedule, "games", season, "eligibility_check")
                    if games.home_score.isna().all() and (
                        (
                            games.kickoff_at.notna().all()
                            and games.kickoff_at.gt(datetime.now(UTC)).all()
                        )
                        or games.source_gameday.gt(datetime.now(UTC).date()).all()
                    ):
                        skipped.append({"season": season, "reason": "season_not_started"})
                        continue
                sources = {
                    name: downloader.fetch(
                        pattern.format(season=season),
                        refresh=(name == "games" or season == current_season),
                        force=force_refresh,
                    )
                    for name, pattern in SOURCES.items()
                }
                snapshot = build_snapshot(season, sources, root, db)
                if (
                    season < current_season
                    and snapshot["summary"]["coverage"]["scored_but_unfinalized_games"]
                ):
                    raise ValueError(
                        f"{season}: scored historical games lack terminal PBP evidence"
                    )
                snapshots.append(snapshot)
                progress(
                    f"  {season}: {snapshot['summary']['coverage']['completed_games']} "
                    f"completed games; {'reused' if snapshot['reused'] else 'validated'}"
                )
            report = {
                "run_id": run_id,
                "skipped_seasons": skipped,
                "started_at": started,
                "finished_at": utc_now(),
                "elapsed_seconds": round(time.perf_counter() - timer, 3),
                "downloaded_bytes": downloader.downloaded_bytes,
                "cache_hits": downloader.cache_hits,
                "revalidated": downloader.revalidated,
                "disk_bytes": sum(
                    path.stat().st_size for path in root.rglob("*") if path.is_file()
                ),
                "seasons": [
                    {
                        "season": s["season"],
                        "snapshot_id": s["id"],
                        "reused": s["reused"],
                        "coverage": s["summary"]["coverage"],
                        "rows": {
                            name: item["published_rows"]
                            for name, item in s["summary"]["datasets"].items()
                        },
                    }
                    for s in snapshots
                ],
            }
            db.publish(snapshots, run_id, report)
            return report
        except Exception as error:
            db.execute(
                "UPDATE ingestion_runs SET status='failed', finished_at=:finished, "
                "error=:error WHERE id=:id",
                {"id": run_id, "finished": utc_now(), "error": str(error)},
            )
            raise
        finally:
            db.close()
