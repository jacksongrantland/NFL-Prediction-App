"""Earlier-fold selection of conservative offensive defaults; no holdout reuse."""

import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from nfl_prediction.data.downloads import file_hash
from nfl_prediction.data.ingest import json_hash
from nfl_prediction.data.participation import labels
from nfl_prediction.features.pipeline import load_history
from nfl_prediction.models.players import OPPORTUNITIES, SIGNED, forecast, summarize

CANDIDATES = {
    "lag_reference": {"allocation": "lag_reference"},
    "capped_lag": {"allocation": "capped_lag"},
    "opportunity": {"allocation": "normalized"},
    "opponent_capped_lag": {"allocation": "capped_lag", "opponent_context": True},
}


def choose(scores: list[dict], positions: list[str]) -> dict:
    """Ties retain the simpler lag workload baseline."""
    selected = {}
    for position in positions:
        losses = {}
        for candidate in CANDIDATES:
            rows = [r for r in scores if r["position"] == position and r["candidate"] == candidate]
            losses[candidate] = (
                sum(r["loss_sum"] for r in rows) / sum(r["n"] for r in rows)
                if rows
                else float("inf")
            )
        selected[position] = min(losses, key=losses.get)
    return selected


def combine(candidates: dict, selected: dict) -> pd.DataFrame:
    result = pd.concat(
        [
            candidates[method].loc[candidates[method].position.eq(position)]
            for position, method in selected.items()
        ],
        ignore_index=True,
    )

    # Reconcile position choices using only pregame expected workloads. The raw
    # lag reference declares a roster-volume floor rather than silently shrinking
    # starters because uncertain backups received position-prior workload.
    result["_group"] = result.game_id + "/" + result.team_id
    grouped = result.groupby("_group", sort=False)
    budgets, remainders = {}, {}
    totals = grouped[[f"unconditional_{s}" for s in OPPORTUNITIES]].sum()
    for key, group in grouped:
        volumes = {
            s: max(
                max(v[s] for v in group.team_volume), float(totals.loc[key, f"unconditional_{s}"])
            )
            for s in OPPORTUNITIES
        }
        volumes["attempts"] = max(volumes["attempts"], volumes["targets"])
        budgets[key] = volumes
        remainders[key] = {
            s: max(0.0, volumes[s] - totals.loc[key, f"unconditional_{s}"]) for s in OPPORTUNITIES
        }
    result["team_volume"] = result._group.map(budgets)
    result["other_opportunities"] = result._group.map(remainders)
    return result.drop(columns="_group")


def run(features: Path, participation: Path, root: Path, output: Path) -> dict:
    eligibility = json.loads((features / "eligibility.json").read_text())
    audit = json.loads((participation / "audit.json").read_text())
    for name, checksum in eligibility["files"].items():
        if file_hash(features / name) != checksum:
            raise ValueError("Feature integrity failure")
    if file_hash(participation / "snaps.parquet") != audit["sha256"]:
        raise ValueError("Participation integrity failure")
    history, lineage = load_history(root)
    if lineage != eligibility["source_snapshots"] or lineage != audit["snapshots"]:
        raise ValueError("Input snapshot lineage differs")
    config = eligibility["config"]
    stats = config["stats"]
    splits = json.loads((features / "splits.json").read_text())
    games = pd.read_parquet(features / "games.parquet")
    players = pd.read_parquet(features / "players.parquet").merge(
        games[["game_id", "eligible_after"]],
        on="game_id",
        validate="many_to_one",
    )
    players["participated"] = labels(players, pd.read_parquet(participation / "snaps.parquet"))
    actual = players[["game_id", "team_id", "player_id", "participated"]].merge(
        history["player_stats"][["game_id", "team_id", "player_id", *stats]],
        on=["game_id", "team_id", "player_id"],
        how="left",
        validate="one_to_one",
    )
    zero = actual.participated.eq(0).fillna(False)
    contradictory = zero & actual[stats].fillna(0).ne(0).any(axis=1)
    actual.loc[contradictory, "participated"] = pd.NA
    actual.loc[zero & ~contradictory, stats] = 0
    players["participated"] = pd.array(actual.participated.to_numpy(), dtype="Int8")
    candidates = {
        name: forecast(players, games, history, {**config, **options})
        for name, options in CANDIDATES.items()
    }
    scores, reports, oof = [], [], []
    for fold in splits["folds"]:
        # Selection uses only folds preceding this validation season.
        selected = choose(scores, config["positions"])
        validation_ids = fold["validation_game_ids"]
        nested = combine(candidates, selected)
        training = nested.loc[nested.game_id.isin(fold["train_game_ids"])]
        _, training_residuals = summarize(training, actual, stats)
        fold_intervals = {
            k: np.quantile(v, [0.1, 0.9]).tolist()
            for k, v in training_residuals.items()
            if len(v) >= 30
        }
        nested = nested.loc[nested.game_id.isin(validation_ids)]
        oof.append(nested)
        metrics, _ = summarize(nested, actual, stats, fold_intervals)
        reports.append(
            {"season": fold["validation_season"], "selected": selected, "metrics": metrics}
        )
        training_actual = actual.loc[actual.game_id.isin(fold["train_game_ids"])]
        scales = training_actual[stats].abs().mean().clip(lower=1).fillna(1)
        for name, rows in candidates.items():
            joined = rows.loc[rows.game_id.isin(validation_ids)].merge(
                actual,
                on=["game_id", "team_id", "player_id"],
                validate="one_to_one",
            )
            for position, group in joined.groupby("position"):
                predicted = group[[f"unconditional_{s}" for s in stats]].to_numpy(dtype=float)
                observed = group[stats].to_numpy(dtype=float, na_value=np.nan)
                loss = np.abs(predicted - observed) / scales.to_numpy()
                loss[~group.participated.notna().to_numpy(), :] = np.nan
                valid = np.isfinite(loss)
                if valid.any():
                    scores.append(
                        {
                            "season": fold["validation_season"],
                            "position": position,
                            "candidate": name,
                            "n": int(valid.sum()),
                            "loss_sum": float(np.nansum(loss)),
                        }
                    )
    selected = choose(scores, config["positions"])
    predictions = combine(candidates, selected)
    nested = pd.concat(oof, ignore_index=True)
    _, residuals = summarize(nested, actual, stats)
    intervals = {
        k: np.quantile(v, [0.1, 0.9]).tolist() for k, v in residuals.items() if len(v) >= 30
    }
    # The observed 2025 test stays frozen. New model evaluation is prospective only.
    predictions = predictions.loc[predictions.season.gt(splits["final_test_season"])].copy()
    for stat in stats:
        for mode in ("conditional", "unconditional"):
            for suffix, i in (("p10", 0), ("p90", 1)):
                bound = predictions.position.map(
                    lambda p: intervals.get(f"{p}/{mode}/{stat}", [np.nan, np.nan])[i]
                )
                values = predictions[f"{mode}_{stat}"] + bound
                predictions[f"{mode}_{stat}_{suffix}"] = (
                    values if stat in SIGNED else values.clip(lower=0)
                )
    identity = json_hash(
        {
            "feature_id": eligibility["feature_id"],
            "audit": audit["participation_id"],
            "code": file_hash(Path(__file__)),
            "forecast_code": file_hash(Path(__file__).with_name("players.py")),
        }
    )
    destination = output / identity
    if destination.exists():
        from nfl_prediction.models.player_io import load_manifest

        return load_manifest(destination)
    staging = output / f".staging-{uuid4().hex}"
    staging.mkdir(parents=True)
    predictions.to_parquet(staging / "projections.parquet", index=False)
    nested.to_parquet(staging / "validation_predictions.parquet", index=False)
    keys = ["game_id", "team_id", "player_id"]
    joined = nested.merge(actual, on=keys, validate="one_to_one")
    for stat in stats:
        joined[f"residual_{stat}"] = (joined[stat] - joined[f"unconditional_{stat}"]).where(
            joined.participated.notna()
        )
    joined.to_parquet(staging / "validation_residuals.parquet", index=False)
    (staging / "intervals.json").write_text(json.dumps(intervals, indent=2) + "\n")
    report = {
        "player_model_id": identity,
        "kind": "selected_offensive_baselines",
        "config": config,
        "selected": selected,
        "selection_scores": scores,
        "validation": reports,
        "feature_id": eligibility["feature_id"],
        "participation_id": audit["participation_id"],
        "source_snapshots": lineage,
        "promotion_status": "local_baseline_default",
        "recommended_for_decisions": False,
        "evaluation_policy": (
            "Nested earlier-season selection; 2025 holdout not rescored. "
            "Prospective 2026+ evaluation pending."
        ),
        "historical_mode": "approximate_corrected_sources",
        "limitations": [
            "Unverified depth roles",
            "Unknown availability",
            "Selected participation coverage",
            "Marginal empirical intervals are not joint draws",
        ],
        "projection_rows": len(predictions),
        "files": {p.name: file_hash(p) for p in staging.iterdir()},
        "path": str(destination.resolve()),
    }
    (staging / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    staging.rename(destination)
    return report
