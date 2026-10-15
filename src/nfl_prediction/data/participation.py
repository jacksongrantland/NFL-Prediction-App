"""Audit snap denominators before interpreting absent players as nonparticipants."""

import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from nfl_prediction.data.downloads import Downloader, file_hash
from nfl_prediction.data.ingest import RELEASE, ingestion_lock, json_hash, save_manifest
from nfl_prediction.data.normalize import TEAM_ALIASES, TEAM_CODES
from nfl_prediction.features.pipeline import load_history
from nfl_prediction.storage.database import Database


def normalize_snaps(raw: pd.DataFrame, history: dict, season: int) -> tuple[pd.DataFrame, dict]:
    required = {
        "game_id",
        "season",
        "team",
        "pfr_player_id",
        "offense_snaps",
        "offense_pct",
        "position",
    }
    if not required.issubset(raw):
        raise ValueError(f"Snap columns missing: {sorted(required - set(raw))}")
    frame = raw.copy()
    if frame.season.isna().any() or not frame.season.eq(season).all():
        raise ValueError("Snap season mismatch")
    frame["team_id"] = frame.team.replace(TEAM_ALIASES)
    if not frame.team_id.isin(TEAM_CODES).all() or frame.pfr_player_id.isna().any():
        raise ValueError("Missing/invalid snap identity")
    if frame.duplicated(["game_id", "team_id", "pfr_player_id"]).any():
        raise ValueError("Duplicate snap key")
    count = pd.to_numeric(frame.offense_snaps, errors="raise")
    pct = pd.to_numeric(frame.offense_pct, errors="raise")
    if (
        count.isna().any()
        or pct.isna().any()
        or (count < 0).any()
        or (count % 1 != 0).any()
        or not pct.between(0, 1).all()
    ):
        raise ValueError("Invalid offensive snap count/percentage")
    frame["offense_snaps"] = count.astype("int32")
    roster = history["weekly_rosters"]
    crosswalk = (
        roster.loc[roster.season.eq(season), ["source_pfr_id", "player_id"]]
        .dropna()
        .drop_duplicates()
    )
    ambiguous = crosswalk.groupby("source_pfr_id").player_id.nunique().gt(1)
    crosswalk = crosswalk.loc[~crosswalk.source_pfr_id.isin(ambiguous.index[ambiguous])]
    frame = frame.merge(
        crosswalk,
        left_on="pfr_player_id",
        right_on="source_pfr_id",
        how="left",
        validate="many_to_one",
    )
    games = history["games"].loc[history["games"].season.eq(season)]
    valid_games = games.loc[games.result_status.eq("final")]
    allowed = {
        (g.game_id, team)
        for g in valid_games.itertuples()
        for team in (g.home_team_id, g.away_team_id)
    }
    frame["final_game_context"] = [
        (game, team) in allowed for game, team in zip(frame.game_id, frame.team_id, strict=True)
    ]
    positive_stats = history["player_stats"].loc[history["player_stats"].season.eq(season)].copy()
    positive_stats = positive_stats.loc[
        positive_stats[["attempts", "carries", "targets"]].fillna(0).sum(axis=1).gt(0)
    ]
    known = set(
        zip(
            frame.loc[frame.offense_snaps.gt(0), "game_id"],
            frame.loc[frame.offense_snaps.gt(0), "player_id"],
            strict=True,
        )
    )
    incomplete = {
        (r.game_id, r.team_id)
        for r in positive_stats.itertuples()
        if (r.game_id, r.player_id) not in known
    }
    complete = {}
    for key, rows in frame.groupby(["game_id", "team_id"]):
        total, maximum = int(rows.offense_snaps.sum()), int(rows.offense_snaps.max())
        mapped_skill = (
            rows.loc[
                rows.position.isin(["QB", "RB", "WR", "TE"]) & rows.offense_snaps.gt(0), "player_id"
            ]
            .notna()
            .all()
        )
        pct_matches = maximum > 0 and np.all(
            np.abs(rows.offense_snaps / maximum - rows.offense_pct) <= 0.011
        )
        complete[key] = bool(
            rows.final_game_context.all()
            and total == 11 * maximum
            and pct_matches
            and mapped_skill
            and key not in incomplete
        )
    frame["team_denominator_verified"] = [
        complete[(g, t)] for g, t in zip(frame.game_id, frame.team_id, strict=True)
    ]
    report = {
        "season": season,
        "snap_rows": len(frame),
        "unmapped_pfr_rows": int(frame.player_id.isna().sum()),
        "team_games": len(complete),
        "verified_team_games": sum(complete.values()),
        "denominator_policy": (
            "11 * maximum snaps; consistent percentages; mapped skill participants; "
            "reconciled final context and positive-stat coverage"
        ),
        "eligibility": "approximate_corrected_sources; unverified absences are unknown",
    }
    return frame, report


def audit(root: Path, output: Path, seasons: list[int] | None = None) -> dict:
    history, lineage = load_history(root, seasons)
    seasons = sorted(map(int, lineage))
    with ingestion_lock(root.resolve()):
        db = Database(root.resolve())
        try:
            downloader = Downloader(root.resolve(), db)
            frames, reports, manifests = [], [], []
            for season in seasons:
                source = downloader.fetch(
                    RELEASE + f"snap_counts/snap_counts_{season}.parquet",
                    refresh=season == max(seasons),
                )
                raw = pd.read_parquet(source.path)
                manifest = save_manifest(
                    db, source, "snap_counts", season, list(raw.columns), root.resolve()
                )
                normalized, report = normalize_snaps(raw, history, season)
                normalized["source_manifest_id"] = manifest
                frames.append(normalized)
                reports.append(report)
                manifests.append(manifest)
            identity = json_hash(
                {"sources": manifests, "history": lineage, "code": file_hash(Path(__file__))}
            )
            destination = output / identity
            if destination.exists():
                report = json.loads((destination / "audit.json").read_text())
                if file_hash(destination / "snaps.parquet") != report["sha256"]:
                    raise ValueError("Participation artifact integrity failure")
                return report
            folder = output / f".staging-{uuid4().hex}"
            folder.mkdir(parents=True)
            path = folder / "snaps.parquet"
            if not path.exists():
                pd.concat(frames, ignore_index=True).to_parquet(path, index=False)
            report = {
                "participation_id": identity,
                "source_manifests": manifests,
                "snapshots": lineage,
                "seasons": reports,
                "sha256": file_hash(path),
                "path": str(destination.resolve()),
            }
            (folder / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
            folder.rename(destination)
            return report
        finally:
            db.close()


def labels(players: pd.DataFrame, snaps: pd.DataFrame) -> pd.Series:
    """Zero is permitted only with a verified complete team-game denominator."""
    keys = ["game_id", "team_id", "player_id"]
    lookup = snaps.dropna(subset=["player_id"])
    if lookup.duplicated(keys).any():
        raise ValueError("Ambiguous GSIS snap mapping")
    complete = snaps.groupby(["game_id", "team_id"]).team_denominator_verified.all().reset_index()
    joined = players[keys].merge(
        lookup[keys + ["offense_snaps"]], on=keys, how="left", validate="many_to_one"
    )
    joined = joined.merge(complete, on=["game_id", "team_id"], how="left", validate="many_to_one")
    values = joined.offense_snaps.gt(0).astype("Int8")
    values.loc[joined.offense_snaps.isna() & ~joined.team_denominator_verified.fillna(False)] = (
        pd.NA
    )
    values.index = players.index
    return values
