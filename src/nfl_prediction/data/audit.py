"""Bounded public-source probes. This is not a historical ingestion pipeline."""

import csv
import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import islice
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

RELEASE_API = "https://api.github.com/repos/nflverse/nflverse-data/releases/tags/"
SCHEDULE_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"
SAMPLE_BYTES = 65_536
SCHEDULE_BYTES = 8 * 1024 * 1024
USER_AGENT = "nfl-prediction-source-audit/0.1 (personal local research)"


@dataclass(frozen=True)
class Dataset:
    name: str
    tag: str
    stem: str
    required: bool
    columns: tuple[str, ...]


DATASETS = (
    Dataset(
        "pbp",
        "pbp",
        "play_by_play",
        True,
        ("game_id", "play_id", "season", "week", "season_type", "posteam", "defteam"),
    ),
    Dataset(
        "player_stats",
        "stats_player",
        "stats_player_week",
        True,
        (
            "player_id",
            "season",
            "week",
            "season_type",
            "game_id",
            "team",
            "attempts",
            "passing_yards",
            "carries",
            "rushing_yards",
            "targets",
            "receptions",
            "receiving_yards",
        ),
    ),
    Dataset(
        "team_stats",
        "stats_team",
        "stats_team_week",
        True,
        ("season", "week", "season_type", "game_id", "team", "opponent_team"),
    ),
    Dataset("rosters", "rosters", "roster", True, ("season", "team", "gsis_id", "position")),
    Dataset(
        "weekly_rosters",
        "weekly_rosters",
        "roster_weekly",
        False,
        ("season", "week", "team", "gsis_id", "position"),
    ),
    Dataset(
        "snap_counts",
        "snap_counts",
        "snap_counts",
        False,
        ("game_id", "pfr_player_id", "season", "week", "team", "offense_snaps"),
    ),
    Dataset(
        "injuries",
        "injuries",
        "injuries",
        False,
        (
            "season",
            "week",
            "game_type",
            "team",
            "gsis_id",
            "report_status",
            "practice_status",
            "date_modified",
        ),
    ),
)
SCHEDULE_COLUMNS = (
    "game_id",
    "season",
    "week",
    "game_type",
    "gameday",
    "gametime",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
)


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def read_bounded(url: str, limit: int, *, prefix: bool) -> tuple[bytes, dict]:
    """Never read an unbounded response, even when a server ignores Range."""
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
    if prefix:
        headers["Range"] = f"bytes=0-{limit - 1}"
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        body = response.read(limit if prefix else limit + 1)
        if len(body) > limit:
            raise ValueError(f"Response exceeded {limit} bytes: {url}")
        metadata = {
            "http_status": response.status,
            "retrieved_at": utc_now(),
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        }
    return body, metadata


def parse_csv(body: bytes, *, complete: bool) -> tuple[list[str], list[dict[str, str]]]:
    """Parse three records from a prefix, or all records from a small complete file."""
    # A prefix can end in the middle of a UTF-8 sequence or quoted record. Read
    # only the first three complete records; never mistake a tail fragment for one.
    if not complete:
        body = body[: body.rfind(b"\n") + 1]
    text = body.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    columns = reader.fieldnames or []
    if not columns or len(columns) != len(set(columns)):
        raise ValueError("Missing or duplicate CSV columns")
    rows = list(reader if complete else islice(reader, 3))
    if not rows or any(None in row or None in row.values() for row in rows):
        raise ValueError("CSV has no complete sample rows or inconsistent row widths")
    return columns, rows


def summarize_sample(body: bytes, columns_needed: tuple[str, ...], *, complete: bool) -> dict:
    columns, rows = parse_csv(body, complete=complete)
    return {
        "bytes_read": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
        "checksum_scope": "full_artifact" if complete else "sample_prefix",
        "columns": columns,
        "missing_required_columns": sorted(set(columns_needed) - set(columns)),
        "rows_examined": len(rows),
        "sample_seasons": sorted({row.get("season", "") for row in rows}),
        "sample_weeks": sorted({row.get("week", "") for row in rows}),
        "sample_game_types": sorted(
            {row.get("season_type", row.get("game_type", "")) for row in rows}
        ),
        "coverage": "artifact_rows" if complete else "first_three_rows_only",
    }


def probe_asset(job: tuple[Dataset, int, dict | None, list[str]]) -> dict:
    dataset, season, asset, formats = job
    entry = {
        "dataset": dataset.name,
        "season": season,
        "required": dataset.required,
        "formats_listed": formats,
        "status": "missing_asset",
        "schema_version": "source-audit/1",
        "source_published_at": None,
        "available_at": None,
    }
    if asset is None:
        return entry
    entry.update(
        {
            "url": asset["browser_download_url"],
            "asset_id": asset["id"],
            "asset_size_bytes": asset["size"],
            "asset_updated_at": asset["updated_at"],
            "upstream_digest": asset.get("digest"),
        }
    )
    try:
        body, metadata = read_bounded(entry["url"], SAMPLE_BYTES, prefix=True)
        entry.update(metadata)
        # A short response only proves completeness if it equals advertised size.
        complete = len(body) == asset["size"]
        entry.update(summarize_sample(body, dataset.columns, complete=complete))
        entry["status"] = "schema_gap" if entry["missing_required_columns"] else "sample_verified"
        if set(entry["sample_seasons"]) != {str(season)}:
            entry["status"] = "season_mismatch"
    except (OSError, ValueError, csv.Error) as error:
        entry.update(status="probe_error", error=f"{type(error).__name__}: {error}")
    return entry


def audit_schedule(seasons: list[int]) -> dict:
    entry = {
        "dataset": "schedules",
        "required": True,
        "url": SCHEDULE_URL,
        "schema_version": "source-audit/1",
        "source_published_at": None,
        "available_at": None,
    }
    try:
        body, metadata = read_bounded(SCHEDULE_URL, SCHEDULE_BYTES, prefix=False)
        entry.update(metadata)
        entry.update(summarize_sample(body, SCHEDULE_COLUMNS, complete=True))
        _, rows = parse_csv(body, complete=True)
        coverage = {}
        for season in seasons:
            selected = [row for row in rows if row["season"] == str(season)]
            coverage[str(season)] = {
                "rows": len(selected),
                "game_types": sorted({row["game_type"] for row in selected}),
                # Scores alone cannot establish final-game status.
                "rows_with_both_scores": sum(
                    row["home_score"] not in ("", "NA") and row["away_score"] not in ("", "NA")
                    for row in selected
                ),
            }
        entry["season_coverage"] = coverage
        entry["status"] = "sample_verified"
        if entry["missing_required_columns"] or any(not c["rows"] for c in coverage.values()):
            entry["status"] = "coverage_gap"
    except (OSError, ValueError, csv.Error, KeyError) as error:
        entry.update(status="probe_error", error=f"{type(error).__name__}: {error}")
    return entry


def run_audit(current_season: int, completed_seasons: int = 6) -> dict:
    """List all target assets and probe bounded CSV samples with four workers."""
    seasons = list(range(current_season - completed_seasons, current_season + 1))
    report = {
        "schema_version": "source-audit/1",
        "started_at": utc_now(),
        "current_season": current_season,
        "requested_seasons": seasons,
        "sample_limit_bytes": SAMPLE_BYTES,
        "release_metadata": [],
        "datasets": [],
        "limitations": [
            "Listed assets and prefix samples do not prove season completeness.",
            "Asset update times do not establish historical pregame availability.",
            "Source URLs and release assets can be replaced; preserve hashes.",
        ],
    }
    jobs = []
    for dataset in DATASETS:
        url = RELEASE_API + dataset.tag
        try:
            body, metadata = read_bounded(url, 4 * 1024 * 1024, prefix=False)
            release = json.loads(body)
            report["release_metadata"].append(
                {
                    "dataset": dataset.name,
                    "url": url,
                    **metadata,
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "release_published_at": release["published_at"],
                }
            )
            assets = {asset["name"]: asset for asset in release["assets"]}
            for season in seasons:
                stem = f"{dataset.stem}_{season}"
                formats = sorted(
                    name[len(stem) + 1 :] for name in assets if name.startswith(stem + ".")
                )
                jobs.append((dataset, season, assets.get(stem + ".csv"), formats))
        except (OSError, ValueError, KeyError) as error:
            # Failure to list a release is unknown availability, not evidence of absence.
            code = error.code if isinstance(error, HTTPError) else None
            for season in seasons:
                report["datasets"].append(
                    {
                        "dataset": dataset.name,
                        "season": season,
                        "required": dataset.required,
                        "status": "metadata_error",
                        "http_status": code,
                        "error": f"{type(error).__name__}: {error}",
                    }
                )
    with ThreadPoolExecutor(max_workers=4) as pool:
        report["datasets"].extend(pool.map(probe_asset, jobs))
    report["datasets"].sort(key=lambda entry: (entry["dataset"], entry["season"]))
    report["schedules"] = audit_schedule(seasons)
    report["finished_at"] = utc_now()
    return report


def write_report(report: dict, output: Path) -> None:
    """Publish one complete audit JSON; no raw datasets are persisted."""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
