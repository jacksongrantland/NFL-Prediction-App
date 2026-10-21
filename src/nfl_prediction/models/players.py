"""Causal offensive opportunity baselines with explicit nonparticipation/missingness."""

import json
import time
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from nfl_prediction.data.downloads import file_hash
from nfl_prediction.data.ingest import json_hash
from nfl_prediction.data.participation import labels
from nfl_prediction.features.pipeline import load_history, smoothed

OPPORTUNITIES = ("attempts", "carries", "targets")
RATES = {
    "completions": "attempts",
    "passing_yards": "attempts",
    "passing_tds": "attempts",
    "passing_interceptions": "attempts",
    "rushing_yards": "carries",
    "rushing_tds": "carries",
    "receptions": "targets",
    "receiving_yards": "targets",
    "receiving_tds": "targets",
}
SIGNED = {"passing_yards", "rushing_yards", "receiving_yards"}


def forecast(
    players: pd.DataFrame, games: pd.DataFrame, history: dict, config: dict
) -> pd.DataFrame:
    """Only earlier known participation labels inform this baseline's probabilities."""
    context = games[["game_id", "eligible_after"]]
    teams = history["team_stats"].merge(context, on="game_id", validate="many_to_one")
    supplied = history["player_stats"]
    supplied = supplied.loc[supplied.position.isin(config["positions"])]
    totals = (
        supplied.groupby(["game_id", "team_id"])[list(OPPORTUNITIES)]
        .sum()
        .add_prefix("supported_")
        .reset_index()
    )
    teams = teams.merge(totals, on=["game_id", "team_id"], how="left", validate="one_to_one")
    for stat in OPPORTUNITIES:
        teams[f"uncovered_{stat}"] = (teams[stat] - teams[f"supported_{stat}"].fillna(0)).clip(
            lower=0
        )
    teams = teams.sort_values("eligible_after")
    output = []
    method = config.get("allocation", "normalized")
    for _, group in players.groupby(["season", "week", "cutoff"], sort=True):
        cutoff = group.cutoff.iloc[0]
        if config.get("forecast_after") and cutoff < pd.Timestamp(config["forecast_after"]):
            continue
        prior = players.loc[players.eligible_after.lt(cutoff) & players.participated.notna()]
        priors = prior.groupby("position").participated.mean().to_dict()
        player_indices = prior.groupby("player_id", sort=False).indices
        participation = prior.participated.to_numpy(dtype=float)
        past_teams = teams.loc[teams.eligible_after.lt(cutoff)]
        by_team = {key: value for key, value in past_teams.groupby("team_id")}
        for (game_id, team), candidates in group.groupby(["game_id", "team_id"], sort=False):
            past = by_team.get(team, past_teams.iloc[:0])
            probabilities = []
            known = []
            healthy = []
            for row in candidates.itertuples():
                indices = player_indices.get(row.player_id, [])[-config["history_games"] :]
                values = participation[indices]
                position_prior = priors.get(row.position)
                probability = (
                    float(
                        (values.sum() + config["prior_games"] * position_prior)
                        / (len(values) + config["prior_games"])
                    )
                    if position_prior is not None
                    else None
                )
                healthy.append(probability if probability is not None else 0.0)
                if (pd.notna(row.game_inactive) and bool(row.game_inactive)) or str(
                    row.injury_designation
                ).lower() == "out":
                    probability = 0.0
                probabilities.append(probability if probability is not None else 0.0)
                known.append(probability is not None)
            probabilities = np.array(probabilities)
            values = candidates[[f"lag_{stat}" for stat in config["stats"]]].to_numpy(dtype=float)
            conditional = np.zeros_like(values)
            volumes = {}
            remainder = {}
            for opportunity in OPPORTUNITIES:
                prior_mean = float(past_teams[opportunity].mean()) if len(past_teams) else 0.0
                volume = smoothed(
                    past, opportunity, prior_mean if np.isfinite(prior_mean) else 0.0, config
                )
                if opportunity == "targets":
                    volume = min(volume, volumes["attempts"])
                if config.get("opponent_context") and len(past_teams):
                    opponent = candidates.opponent_team_id.iloc[0]
                    conceded = past_teams.loc[past_teams.opponent_team_id.eq(opponent)]
                    if len(conceded) >= 4 and prior_mean > 0:
                        volume *= float(
                            np.clip(
                                smoothed(conceded, opportunity, prior_mean, config) / prior_mean,
                                0.75,
                                1.25,
                            )
                        )
                if opportunity == "targets":
                    volume = min(volume, volumes["attempts"])
                if method == "lag_reference":
                    index = config["stats"].index(opportunity)
                    reference_total = float(np.dot(healthy, np.maximum(values[:, index], 0)))
                    # Unknown competing depth roles can make the roster workload sum
                    # exceed the historical team estimate. Expose that reconciliation.
                    volume = max(volume, reference_total)
                volumes[opportunity] = volume
                index = config["stats"].index(opportunity)
                weights = np.maximum(values[:, index], 0)
                expected_weights = probabilities * weights
                # Explicit omitted-role/unresolved-player allocation from prior team totals.
                prior_total = past[opportunity].sum()
                fraction = (
                    float(past[f"uncovered_{opportunity}"].sum() / prior_total)
                    if prior_total > 0
                    else 0.0
                )
                fraction = float(np.clip(fraction, 0, 1))
                other_weight = expected_weights.sum() * fraction / max(1 - fraction, 1e-9)
                denominator = expected_weights.sum() + other_weight + weights - expected_weights
                if method == "capped_lag":
                    # Preserve lag workload when below team capacity; only scale down.
                    # Conditional counterfactual activates this player and holds others fixed.
                    denominator = np.maximum(denominator, volume)
                conditional[:, index] = np.divide(
                    volume * weights, denominator, out=np.zeros(len(weights)), where=denominator > 0
                )
                if method == "lag_reference":
                    released = max(0.0, reference_total - float(expected_weights.sum()))
                    multiplier = (
                        1 + released / expected_weights.sum() if expected_weights.sum() > 0 else 1.0
                    )
                    conditional[:, index] = weights * multiplier
                remainder[opportunity] = max(
                    0.0, volume - float(np.sum(conditional[:, index] * probabilities))
                )
            for stat, opportunity in RATES.items():
                index, source = config["stats"].index(stat), config["stats"].index(opportunity)
                rate = np.divide(
                    values[:, index],
                    values[:, source],
                    out=np.zeros(len(values)),
                    where=values[:, source] > 0,
                )
                if stat not in SIGNED:
                    rate = np.clip(rate, 0, 1)
                conditional[:, index] = conditional[:, source] * rate
            for i, row in enumerate(candidates.itertuples()):
                record = {
                    "game_id": game_id,
                    "player_id": row.player_id,
                    "team_id": team,
                    "position": row.position,
                    "season": int(row.season),
                    "week": int(row.week),
                    "cutoff": row.cutoff,
                    "offense_participation_probability": float(probabilities[i])
                    if known[i]
                    else None,
                    "availability_unknown": bool(row.availability_unknown),
                    "role_unknown": True,
                    "allocation_method": method,
                    "opponent_context": bool(config.get("opponent_context")),
                    "role_policy": "Lag workload; depth order unverified; no starter guarantee.",
                    "support": "baseline_approximate" if known[i] else "unsupported_cold_start",
                    "team_volume": volumes,
                    "team_volume_policy": (
                        "Historical volume floored at roster lag workload; "
                        "unresolved roles may inflate volume."
                    )
                    if method == "lag_reference"
                    else "historical_team_volume",
                    "other_opportunities": remainder,
                }
                for j, stat in enumerate(config["stats"]):
                    record[f"conditional_{stat}"] = float(conditional[i, j]) if known[i] else None
                    record[f"unconditional_{stat}"] = (
                        float(probabilities[i] * conditional[i, j]) if known[i] else None
                    )
                    record[f"baseline_{stat}"] = (
                        float(probabilities[i] * values[i, j]) if known[i] else None
                    )
                output.append(record)
    return pd.DataFrame(output)


def summarize(
    rows: pd.DataFrame, actual: pd.DataFrame, stats: list[str], intervals: dict | None = None
) -> tuple[list, dict]:
    joined = rows.merge(actual, on=["game_id", "team_id", "player_id"], validate="one_to_one")
    reports, residuals = [], {}
    for position, group in joined.groupby("position"):
        for mode in ("conditional", "unconditional"):
            for stat in stats:
                eligible = (
                    group[stat].notna()
                    & group[f"{mode}_{stat}"].notna()
                    & group.participated.notna()
                )
                if mode == "conditional":
                    eligible &= group.participated.eq(1)
                selected = group.loc[eligible]
                if selected.empty:
                    continue
                error = selected[f"{mode}_{stat}"].to_numpy() - selected[stat].to_numpy(dtype=float)
                key = f"{position}/{mode}/{stat}"
                residuals[key] = (-error).tolist()
                report = {
                    "position": position,
                    "mode": mode,
                    "stat": stat,
                    "n": len(error),
                    "mae": float(np.abs(error).mean()),
                    "bias": float(error.mean()),
                    "workload_bucket": "all",
                }
                if mode == "unconditional":
                    baseline_error = selected[f"baseline_{stat}"].to_numpy() - selected[
                        stat
                    ].to_numpy(dtype=float)
                    report["lag_baseline_mae"] = float(np.abs(baseline_error).mean())
                if intervals and key in intervals:
                    low, high = intervals[key]
                    report["nominal_interval"] = 0.8
                    report["interval_coverage"] = float(
                        ((error + low <= 0) & (error + high >= 0)).mean()
                    )
                reports.append(report)
                workload = (
                    selected[[f"baseline_{stat}" for stat in OPPORTUNITIES]].sum(axis=1).to_numpy()
                )
                for bucket, mask in (
                    ("low", workload < 1),
                    ("medium", (workload >= 1) & (workload < 10)),
                    ("high", workload >= 10),
                ):
                    if mask.any():
                        reports.append(
                            {
                                **report,
                                "workload_bucket": bucket,
                                "n": int(mask.sum()),
                                "mae": float(np.abs(error[mask]).mean()),
                                "bias": float(error[mask].mean()),
                                **(
                                    {"lag_baseline_mae": float(np.abs(baseline_error[mask]).mean())}
                                    if mode == "unconditional"
                                    else {}
                                ),
                                **(
                                    {
                                        "interval_coverage": float(
                                            (
                                                (error[mask] + low <= 0) & (error[mask] + high >= 0)
                                            ).mean()
                                        )
                                    }
                                    if intervals and key in intervals
                                    else {}
                                ),
                            }
                        )
    return reports, residuals


def run(feature_path: Path, participation_path: Path, root: Path, output: Path) -> dict:
    start = time.perf_counter()
    eligibility = json.loads((feature_path / "eligibility.json").read_text())
    for name, checksum in eligibility["files"].items():
        if file_hash(feature_path / name) != checksum:
            raise ValueError("Feature integrity failure")
    audit = json.loads((participation_path / "audit.json").read_text())
    if file_hash(participation_path / "snaps.parquet") != audit["sha256"]:
        raise ValueError("Participation artifact integrity failure")
    history, lineage = load_history(root)
    if lineage != eligibility["source_snapshots"] or audit["snapshots"] != lineage:
        raise ValueError("Participation, features and historical snapshot lineage differ")
    identity = json_hash(
        {
            "features": eligibility["feature_id"],
            "participation": audit["participation_id"],
            "code": file_hash(Path(__file__)),
        }
    )
    destination = output / identity
    if destination.exists():
        return json.loads((destination / "manifest.json").read_text())
    games = pd.read_parquet(feature_path / "games.parquet")
    players = pd.read_parquet(feature_path / "players.parquet")
    players = players.merge(
        games[["game_id", "eligible_after"]], on="game_id", validate="many_to_one"
    )
    snaps = pd.read_parquet(participation_path / "snaps.parquet")
    players["participated"] = labels(players, snaps)
    stats = eligibility["config"]["stats"]
    actual = players[["game_id", "team_id", "player_id", "participated"]].merge(
        history["player_stats"][["game_id", "team_id", "player_id", *stats]],
        on=["game_id", "team_id", "player_id"],
        how="left",
        validate="one_to_one",
    )
    no_participation = actual.participated.eq(0).fillna(False)
    contradiction = no_participation & actual[stats].fillna(0).ne(0).any(axis=1)
    actual.loc[contradiction, "participated"] = pd.NA
    actual.loc[no_participation & ~contradiction, stats] = 0
    players["participated"] = pd.array(actual.participated.to_numpy(), dtype="Int8")
    predictions = forecast(players, games, history, eligibility["config"])
    splits = json.loads((feature_path / "splits.json").read_text())
    reports = []
    for fold in splits["folds"]:
        training = predictions.loc[predictions.game_id.isin(fold["train_game_ids"])]
        _, residuals = summarize(training, actual, stats)
        intervals = {
            key: np.quantile(values, [0.1, 0.9]).tolist()
            for key, values in residuals.items()
            if len(values) >= 30
        }
        validation = predictions.loc[predictions.game_id.isin(fold["validation_game_ids"])]
        metrics, _ = summarize(validation, actual, stats, intervals)
        reports.append({"season": fold["validation_season"], "metrics": metrics})
    training = predictions.loc[predictions.game_id.isin(splits["final_train_game_ids"])]
    _, residuals = summarize(training, actual, stats)
    intervals = {
        key: np.quantile(values, [0.1, 0.9]).tolist()
        for key, values in residuals.items()
        if len(values) >= 30
    }
    validation_ids = {game for fold in splits["folds"] for game in fold["validation_game_ids"]}
    _, validation_residuals = summarize(
        predictions.loc[predictions.game_id.isin(validation_ids)], actual, stats
    )
    final, _ = summarize(
        predictions.loc[predictions.game_id.isin(splits["final_test_game_ids"])],
        actual,
        stats,
        intervals,
    )
    calibration_cutoff = games.loc[
        games.game_id.isin(splits["final_train_game_ids"]), "eligible_after"
    ].max()
    interval_eligible = predictions.cutoff.gt(calibration_cutoff)
    for stat in stats:
        for mode in ("conditional", "unconditional"):
            for suffix, quantile in (("p10", 0), ("p90", 1)):
                bounds = predictions.position.map(
                    lambda position: intervals.get(f"{position}/{mode}/{stat}", [np.nan, np.nan])[
                        quantile
                    ]
                )
                value = predictions[f"{mode}_{stat}"] + bounds
                if stat not in SIGNED:
                    value = value.clip(lower=0)
                predictions[f"{mode}_{stat}_{suffix}"] = value.where(interval_eligible)
    evaluated = predictions.loc[predictions.game_id.isin(splits["final_test_game_ids"])].merge(
        actual, on=["game_id", "team_id", "player_id"]
    )
    known = evaluated.participated.notna() & evaluated.offense_participation_probability.notna()
    probability = evaluated.loc[known, "offense_participation_probability"].to_numpy(dtype=float)
    outcome = evaluated.loc[known, "participated"].to_numpy(dtype=float)
    participation_report = {
        "n": int(known.sum()),
        "brier": float(np.mean((probability - outcome) ** 2)) if len(outcome) else None,
    }
    folder = output / f".staging-{uuid4().hex}"
    folder.mkdir(parents=True)
    predictions.to_parquet(folder / "projections.parquet", index=False)
    actual.to_parquet(folder / "actual_eligibility.parquet", index=False)
    (folder / "residuals.json").write_text(json.dumps(validation_residuals) + "\n")
    (folder / "intervals.json").write_text(json.dumps(intervals, indent=2) + "\n")
    report = {
        "player_model_id": identity,
        "kind": "opportunity_participation_baseline",
        "feature_id": eligibility["feature_id"],
        "participation_id": audit["participation_id"],
        "config": eligibility["config"],
        "projection_rows": len(predictions),
        "known_participation_rows": int(players.participated.notna().sum()),
        "unknown_participation_rows": int(players.participated.isna().sum()),
        "missing_actual_stat_rows_despite_positive_snaps": int(
            (actual.participated.eq(1) & actual[stats].isna().all(axis=1)).sum()
        ),
        "contradictory_snap_stat_rows": int(contradiction.sum()),
        "validation": reports,
        "final_test_season": splits["final_test_season"],
        "final_test": final,
        "historical_mode": "approximate_corrected_sources",
        "promotion_status": "baseline_candidate",
        "participation_final_test": participation_report,
        "interval_calibration_cutoff": calibration_cutoff.isoformat(),
        "uncertainty_policy": "80% empirical residual intervals; no inferred injury weights",
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "files": {p.name: file_hash(p) for p in folder.iterdir()},
        "path": str(destination.resolve()),
    }
    (folder / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    folder.rename(destination)
    return report
