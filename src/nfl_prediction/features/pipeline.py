"""Weekly frozen features from completed prior games, with explicit timing limits."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import text

from nfl_prediction.data.downloads import file_hash
from nfl_prediction.data.ingest import json_hash, verify_snapshot
from nfl_prediction.data.snapshots import as_of
from nfl_prediction.storage.database import Database

DEFAULT_CONFIG = Path(__file__).parents[3] / "config" / "features.json"


def load_history(root: Path, seasons: list[int] | None = None) -> tuple[dict, dict]:
    db = Database(root.resolve())
    try:
        with db.engine.connect() as connection:
            entries = (
                connection.execute(
                    text(
                        "SELECT a.season, s.id, s.path FROM active_seasons a "
                        "JOIN snapshots s ON a.snapshot_id=s.id ORDER BY a.season"
                    )
                )
                .mappings()
                .all()
            )
    finally:
        db.close()
    entries = [e for e in entries if seasons is None or e["season"] in seasons]
    if not entries or (seasons and set(seasons) != {e["season"] for e in entries}):
        raise ValueError("Requested seasons must all have published snapshots")
    frames = {key: [] for key in ("games", "team_stats", "player_stats", "weekly_rosters")}
    lineage = {}
    for entry in entries:
        folder = Path(entry["path"])
        verify_snapshot(folder)
        lineage[str(entry["season"])] = entry["id"]
        for key in frames:
            frames[key].append(pd.read_parquet(folder / f"{key}.parquet"))
    return {key: pd.concat(values, ignore_index=True) for key, values in frames.items()}, lineage


def smoothed(history: pd.DataFrame, column: str, prior: float, config: dict) -> float:
    values = history.tail(config["history_games"])[column].astype(float).to_numpy()
    valid = np.isfinite(values)
    weights = np.exp2(-np.arange(len(values) - 1, -1, -1) / config["half_life_games"])
    return float(
        (np.dot(values[valid], weights[valid]) + config["prior_games"] * prior)
        / (weights[valid].sum() + config["prior_games"])
    )


def player_lags(history: np.ndarray, priors: np.ndarray, config: dict) -> dict:
    """Compute all stat columns together instead of repeating pandas work per stat."""
    values = history[-config["history_games"] :]
    valid = np.isfinite(values)
    weights = np.exp2(-np.arange(len(values) - 1, -1, -1) / config["half_life_games"])[:, None]
    result = (
        (np.where(valid, values, 0) * weights).sum(axis=0) + config["prior_games"] * priors
    ) / ((valid * weights).sum(axis=0) + config["prior_games"])
    return {
        f"lag_{stat}": float(value) for stat, value in zip(config["stats"], result, strict=True)
    }


def build_frames(
    history: dict, config: dict, *, observation_reader=None, live_cutoff=None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    games = history["games"].copy()
    games["kickoff_at"] = pd.to_datetime(games.kickoff_at, utc=True)
    games = games.loc[games.game_type.isin(["REG", "POST"]) & games.kickoff_at.notna()].copy()
    if games.empty:
        raise ValueError("No games with usable kickoffs")
    # No observed end timestamp exists in these sources. This is conservative,
    # explicit approximate eligibility, never a claimed observed final whistle.
    games["eligible_after"] = games.kickoff_at + pd.Timedelta(
        hours=config["completion_delay_hours"]
    )
    games["cutoff"] = games.groupby(["season", "week"]).kickoff_at.transform("min")
    if live_cutoff is not None:
        now = pd.Timestamp(live_cutoff)
        if now.tzinfo is None:
            raise ValueError("Live cutoff must be timezone-aware")
        games.loc[games.kickoff_at.gt(now), "cutoff"] = now
    context = games.loc[
        games.result_status.eq("final"), ["game_id", "eligible_after", "kickoff_at"]
    ]
    stats = history["player_stats"].merge(context, on="game_id", validate="many_to_one")
    stats = stats.sort_values(["kickoff_at", "game_id", "player_id"])
    final = games.loc[games.result_status.eq("final")].sort_values(["kickoff_at", "game_id"])
    team_rows = []
    for game in final.itertuples():
        for home in (True, False):
            team_rows.append(
                {
                    "team_id": game.home_team_id if home else game.away_team_id,
                    "points": float(game.home_score if home else game.away_score),
                    "allowed": float(game.away_score if home else game.home_score),
                    "kickoff_at": game.kickoff_at,
                    "eligible_after": game.eligible_after,
                }
            )
    team_history = pd.DataFrame(
        team_rows, columns=["team_id", "points", "allowed", "kickoff_at", "eligible_after"]
    )
    roster = history["weekly_rosters"]
    roster_groups = roster.groupby(["season", "week", "game_type", "team_id"], sort=False).indices
    game_features, player_features = [], []
    for _, group in games.groupby(["season", "week", "cutoff"], sort=True):
        cutoff = group.cutoff.iloc[0]
        prior_teams = team_history.loc[team_history.eligible_after.lt(cutoff)]
        prior_players = stats.loc[stats.eligible_after.lt(cutoff)]
        league_points = (
            float(prior_teams.points.mean()) if len(prior_teams) else config["default_team_points"]
        )
        by_team = {key: value for key, value in prior_teams.groupby("team_id")}
        by_player = prior_players.groupby("player_id", sort=False).indices
        prior_values = prior_players[config["stats"]].to_numpy(dtype=float)
        prior_team_ids = prior_players.team_id.to_numpy()
        position_priors = prior_players.groupby("position")[config["stats"]].mean()
        position_vectors = {
            position: row.fillna(0).to_numpy(dtype=float)
            for position, row in position_priors.iterrows()
        }
        for game in group.itertuples():
            row = {
                "game_id": game.game_id,
                "season": int(game.season),
                "week": int(game.week),
                "game_type": game.game_type,
                "cutoff": cutoff,
                "kickoff_at": game.kickoff_at,
                "eligible_after": game.eligible_after,
                "result_status": game.result_status,
                "home_team_id": game.home_team_id,
                "away_team_id": game.away_team_id,
                "home_score": game.home_score,
                "away_score": game.away_score,
                "eligibility": "approximate_corrected_sources",
            }
            observations = (
                observation_reader(game.season, game.game_id, cutoff) if observation_reader else {}
            )
            avail = {p["player_id"]: p for p in observations.get("availability", [])}
            for side, team, opponent in (
                ("home", game.home_team_id, game.away_team_id),
                ("away", game.away_team_id, game.home_team_id),
            ):
                past = by_team.get(team, prior_teams.iloc[:0])
                row[f"{side}_points"] = smoothed(past, "points", league_points, config)
                row[f"{side}_allowed"] = smoothed(past, "allowed", league_points, config)
                row[f"{side}_history_games"] = len(past)
                row[f"{side}_rest_days"] = (
                    min(60.0, (game.kickoff_at - past.kickoff_at.iloc[-1]).total_seconds() / 86400)
                    if len(past)
                    else config["default_rest_days"]
                )
                opponent_history = by_team.get(opponent, prior_teams.iloc[:0])
                opponent_allowed = smoothed(opponent_history, "allowed", league_points, config)
                indices = roster_groups.get((game.season, game.week, game.game_type, team), [])
                candidates = roster.iloc[indices]
                prospective_roster = (
                    live_cutoff is not None
                    and game.kickoff_at > now
                    and observations.get("roster_freshness") == "observed"
                )
                if prospective_roster:
                    candidates = pd.DataFrame(observations.get("roster", []))
                    if candidates.empty:
                        candidates = roster.iloc[:0]
                candidates = candidates.loc[candidates.position.isin(config["positions"])]
                for player in candidates.drop_duplicates("player_id").itertuples():
                    player_indices = by_player.get(player.player_id, [])
                    values = {
                        "game_id": game.game_id,
                        "season": int(game.season),
                        "week": int(game.week),
                        "cutoff": cutoff,
                        "player_id": player.player_id,
                        "team_id": team,
                        "opponent_team_id": opponent,
                        "position": player.position,
                        "is_home": int(side == "home"),
                        "history_games": len(player_indices),
                        "prior_team_id": prior_team_ids[player_indices[-1]]
                        if len(player_indices)
                        else None,
                        "role_unknown": True,
                        "roster_status": player.roster_status,
                        "roster_eligibility": "prospective_observed_roster"
                        if prospective_roster
                        else "approximate_corrected_weekly_roster",
                        "roster_batch_id": observations.get("roster_batch_id")
                        if prospective_roster
                        else None,
                        "availability_unknown": player.player_id not in avail
                        or avail[player.player_id].get("freshness") != "observed",
                    }
                    for name in ("injury_designation", "practice_participation", "game_inactive"):
                        values[name] = avail.get(player.player_id, {}).get(name)
                    for name in ("batch_id", "observed_at", "recorded_at"):
                        values[f"availability_{name}"] = avail.get(player.player_id, {}).get(name)
                    priors = position_vectors.get(player.position, np.zeros(len(config["stats"])))
                    values.update(player_lags(prior_values[player_indices], priors, config))
                    values["opponent_allowed"] = opponent_allowed
                    player_features.append(values)
            game_features.append(row)
    return pd.DataFrame(game_features), pd.DataFrame(player_features)


def split_manifest(games: pd.DataFrame) -> dict:
    now = datetime.now(UTC)
    current = now.year - (now.month < 3)
    completed = [
        int(season)
        for season, rows in games.groupby("season")
        if season < current and rows.result_status.eq("final").all()
    ]
    if len(completed) < 3:
        raise ValueError("Need at least three eligible completed seasons for train/validation/test")
    test = max(completed)
    eligible = games.loc[games.result_status.eq("final") & games.season.isin(completed)]

    def ids(rows):
        return rows.sort_values(["cutoff", "game_id"]).game_id.tolist()

    folds = []
    for validation in completed[1:-1]:
        val = eligible.loc[eligible.season.eq(validation)]
        start = val.cutoff.min()
        train = eligible.loc[eligible.season.lt(validation) & eligible.eligible_after.lt(start)]
        folds.append(
            {
                "validation_season": validation,
                "train_game_ids": ids(train),
                "validation_game_ids": ids(val),
            }
        )
    test_rows = eligible.loc[eligible.season.eq(test)]
    return {
        "version": "splits/1",
        "grouping": "complete_season_week",
        "final_test_season": test,
        "folds": folds,
        "final_train_game_ids": ids(
            eligible.loc[
                eligible.season.lt(test) & eligible.eligible_after.lt(test_rows.cutoff.min())
            ]
        ),
        "final_test_game_ids": ids(test_rows),
        "excluded_nonfinal_or_current_game_ids": ids(
            games.loc[~games.game_id.isin(eligible.game_id)]
        ),
    }


def prepare(
    root: Path,
    output: Path,
    *,
    seasons: list[int] | None = None,
    config_path: Path = DEFAULT_CONFIG,
    include_observations: bool = True,
    live_cutoff=None,
) -> dict:
    start = time.perf_counter()
    config = json.loads(config_path.read_text())
    if (
        config["history_games"] < 1
        or min(config["half_life_games"], config["prior_games"], config["completion_delay_hours"])
        <= 0
    ):
        raise ValueError("History, shrinkage and timing configuration must be positive")
    history, lineage = load_history(root, seasons)
    db = Database(root.resolve())
    try:
        with db.engine.connect() as connection:
            first_observed = dict(
                connection.execute(
                    text("SELECT season, min(recorded_at) FROM observation_batches GROUP BY season")
                ).all()
            )
    finally:
        db.close()

    def reader(season, game, cutoff):
        if season not in first_observed or cutoff < pd.Timestamp(first_observed[season]):
            return {}
        return as_of(season, game, cutoff, root)

    games, players = build_frames(
        history,
        config,
        observation_reader=reader if include_observations else None,
        live_cutoff=live_cutoff,
    )
    splits = split_manifest(games)
    output.mkdir(parents=True, exist_ok=True)
    identity = json_hash(
        {
            "config": config,
            "sources": lineage,
            "code": file_hash(Path(__file__)),
            "game_features": games.to_json(date_format="iso"),
            "player_features": players.to_json(date_format="iso"),
        }
    )
    destination = output / identity
    if destination.exists():
        report = json.loads((destination / "eligibility.json").read_text())
        for name, checksum in report["files"].items():
            if file_hash(destination / name) != checksum:
                raise ValueError("Feature artifact integrity failure")
        return {**report, "path": str(destination.resolve()), "reused": True}
    staging = output / f".staging-{uuid4().hex}"
    staging.mkdir()
    games.to_parquet(staging / "games.parquet", index=False)
    players.to_parquet(staging / "players.parquet", index=False)
    (staging / "splits.json").write_text(json.dumps(splits, indent=2) + "\n")
    report = {
        "feature_id": identity,
        "live_cutoff": pd.Timestamp(live_cutoff).isoformat() if live_cutoff is not None else None,
        "config": config,
        "source_snapshots": lineage,
        "availability_batch_ids": sorted(players.availability_batch_id.dropna().unique().tolist())
        if len(players)
        else [],
        "game_rows": len(games),
        "player_rows": len(players),
        "strict_historical_rows": 0,
        "historical_mode": "approximate_corrected_sources",
        "availability_policy": "local observed_at and recorded_at by frozen week cutoff",
        "completion_policy": (
            "final PBP reconciliation plus kickoff + "
            f"{config['completion_delay_hours']}h approximation"
        ),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "files": {p.name: file_hash(p) for p in staging.iterdir()},
    }
    (staging / "eligibility.json").write_text(json.dumps(report, indent=2) + "\n")
    staging.rename(destination)
    return {**report, "path": str(destination.resolve())}
