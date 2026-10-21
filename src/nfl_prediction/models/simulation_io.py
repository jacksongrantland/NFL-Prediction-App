"""Verified local simulation artifacts and bounded validation-week evaluation."""

import json
import time
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from nfl_prediction.data.downloads import file_hash
from nfl_prediction.data.ingest import json_hash
from nfl_prediction.models.games import load, predict
from nfl_prediction.models.player_io import load_manifest
from nfl_prediction.models.simulation import simulate, validate


def run(
    game_model: Path,
    player_model: Path,
    features: Path,
    output: Path,
    *,
    season: int,
    week: int,
    count: int = 500,
    seed: int = 2026,
    validation: bool = False,
) -> dict:
    start = time.perf_counter()
    model, game_manifest = load(game_model)
    player_manifest = load_manifest(player_model)
    eligibility = json.loads((features / "eligibility.json").read_text())
    for name, checksum in eligibility["files"].items():
        if file_hash(features / name) != checksum:
            raise ValueError("Feature integrity failure")
    if (
        eligibility["config"] != game_manifest["config"]
        or eligibility["config"] != player_manifest["config"]
    ):
        raise ValueError("Input feature schema differs from models")
    if player_manifest["feature_id"] != eligibility["feature_id"]:
        raise ValueError("Player projections must use this feature snapshot")
    games = pd.read_parquet(features / "games.parquet")
    games = games.loc[games.season.eq(season) & games.week.eq(week)].copy()
    if games.empty:
        raise ValueError("No games for requested week")
    if validation:
        estimates = pd.read_parquet(game_model / "validation_predictions.parquet")
        players = pd.read_parquet(player_model / "validation_predictions.parquet")
        games = games.merge(
            estimates[["game_id", "home_expected", "away_expected"]],
            on="game_id",
            validate="one_to_one",
        )
        if games.empty:
            raise ValueError("Requested games are not earlier validation predictions")
    else:
        estimates = predict(model, games.reset_index(drop=True))
        games["home_expected"] = estimates.home_expected.to_numpy()
        games["away_expected"] = estimates.away_expected.to_numpy()
        players = pd.read_parquet(player_model / "projections.parquet")
    summary, team_frames, player_frames, errors = [], [], [], []
    for index, game in enumerate(games.to_dict("records")):
        subset = players.loc[players.game_id.eq(game["game_id"])]
        result = simulate(game, subset, count=count, seed=seed + index)
        validate(result)
        summary.append(result["summary"])
        team_frames.append(result["teams"].assign(game_id=game["game_id"]))
        player_frames.append(result["players"].assign(game_id=game["game_id"]))
        if validation and game["result_status"] == "final":
            home, away = float(game["home_score"]), float(game["away_score"])
            probability = np.array([summary[-1][k] for k in ("home_win", "tie", "away_win")])
            outcome = int(0 if home > away else 1 if home == away else 2)
            errors.append(
                {
                    "game_id": game["game_id"],
                    "brier": float(((probability - np.eye(3)[outcome]) ** 2).sum()),
                    "log_loss": float(-np.log(max(probability[outcome], 1 / (count + 3)))),
                    "home_probability": float(probability[0]),
                    "home_won": outcome == 0,
                    "margin_absolute_error": abs(
                        summary[-1]["home_expected"] - summary[-1]["away_expected"] - home + away
                    ),
                    "home_covered": summary[-1]["home_p10_p90"][0]
                    <= home
                    <= summary[-1]["home_p10_p90"][1],
                    "away_covered": summary[-1]["away_p10_p90"][0]
                    <= away
                    <= summary[-1]["away_p10_p90"][1],
                }
            )
    identity = json_hash(
        {
            "game_model": game_manifest["model_id"],
            "player_model": player_manifest["player_model_id"],
            "features": eligibility["feature_id"],
            "season": season,
            "week": week,
            "count": count,
            "seed": seed,
            "validation": validation,
            "code": file_hash(Path(__file__)),
            "simulation_code": file_hash(Path(__file__).with_name("simulation.py")),
        }
    )
    destination = output / identity
    if destination.exists():
        return read(destination)
    staging = output / f".staging-{uuid4().hex}"
    staging.mkdir(parents=True)
    pd.concat(team_frames).to_parquet(staging / "team_draws.parquet", index=False)
    pd.concat(player_frames).to_parquet(staging / "player_draws.parquet", index=False)
    (staging / "summaries.json").write_text(json.dumps(summary, indent=2) + "\n")
    metrics = None
    player_metrics = []
    if validation:
        actuals = pd.read_parquet(player_model / "validation_residuals.parquet")
        evaluated = []
        for game_summary in summary:
            game_actual = actuals.loc[actuals.game_id.eq(game_summary["game_id"])]
            for player in game_summary["player_summaries"]:
                actual = game_actual.loc[
                    game_actual.team_id.eq(player["team_id"])
                    & game_actual.player_id.eq(player["player_id"])
                ]
                if actual.empty or pd.isna(actual.iloc[0].participated):
                    continue
                for stat, distribution in player["stats"].items():
                    value = actual.iloc[0][stat]
                    if pd.notna(value):
                        evaluated.append(
                            {
                                "position": actual.iloc[0].position,
                                "stat": stat,
                                "error": distribution["mean"] - float(value),
                                "covered": distribution["p10"] <= value <= distribution["p90"],
                            }
                        )
        if evaluated:
            for (position, stat), group in pd.DataFrame(evaluated).groupby(["position", "stat"]):
                player_metrics.append(
                    {
                        "position": position,
                        "stat": stat,
                        "n": len(group),
                        "mae": float(group.error.abs().mean()),
                        "bias": float(group.error.mean()),
                        "interval_coverage": float(group.covered.mean()),
                    }
                )
    if errors:
        frame = pd.DataFrame(errors)
        metrics = {
            "n": len(frame),
            "brier": float(frame.brier.mean()),
            "log_loss": float(frame.log_loss.mean()),
            "margin_mae": float(frame.margin_absolute_error.mean()),
            "score_80_interval_coverage": float(
                pd.concat([frame.home_covered, frame.away_covered]).mean()
            ),
            "reliability": [],
            "player_metrics": player_metrics,
        }
        for low in (0, 0.2, 0.4, 0.6, 0.8):
            bucket = frame.loc[
                frame.home_probability.ge(low)
                & (
                    frame.home_probability.lt(low + 0.2)
                    if low < 0.8
                    else frame.home_probability.le(1)
                )
            ]
            if len(bucket):
                metrics["reliability"].append(
                    {
                        "low": low,
                        "n": len(bucket),
                        "predicted": float(bucket.home_probability.mean()),
                        "observed": float(bucket.home_won.mean()),
                    }
                )
        (staging / "evaluation.json").write_text(
            json.dumps({"metrics": metrics, "games": errors}, indent=2) + "\n"
        )
    manifest = {
        "simulation_id": identity,
        "game_model_id": game_manifest["model_id"],
        "player_model_id": player_manifest["player_model_id"],
        "feature_id": eligibility["feature_id"],
        "source_snapshots": eligibility["source_snapshots"],
        "seed": seed,
        "count": count,
        "season": season,
        "week": week,
        "games": len(games),
        "kind": "retrospective_validation" if validation else "unpublished_preview",
        "recommended_for_decisions": False,
        "accounting_version": "simulation/1",
        "evaluation": metrics,
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "files": {p.name: file_hash(p) for p in staging.iterdir()},
        "path": str(destination.resolve()),
    }
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    staging.rename(destination)
    return manifest


def read(folder: Path) -> dict:
    manifest = json.loads((folder / "manifest.json").read_text())
    for name, checksum in manifest["files"].items():
        if file_hash(folder / name) != checksum:
            raise ValueError("Simulation integrity failure")
    return manifest
