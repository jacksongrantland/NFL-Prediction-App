"""Audited team kicking and limited defense baselines; no invented player assignments."""

import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from nfl_prediction.api.reads import query
from nfl_prediction.data.downloads import file_hash
from nfl_prediction.data.ingest import json_hash
from nfl_prediction.features.pipeline import load_history, smoothed

FIELDS = ("fg_att", "fg_made", "pat_att", "pat_made", "def_sacks", "def_interceptions")
GROUPS = {
    "field_goals": ["fg_att", "fg_made"],
    "extra_points": ["pat_att", "pat_made"],
    "sacks": ["def_sacks"],
    "interceptions": ["def_interceptions"],
}
METHODS = ("league", "own", "opponent")


def load_actuals(root: Path):
    history, lineage = load_history(root)
    records, audit = [], []
    for season, identity in lineage.items():
        snapshot = query(root, "SELECT * FROM snapshots WHERE id=?", (identity,))[0]
        summary = json.loads(snapshot["summary_json"])
        manifest_id = summary["source_manifests"]["team_stats"]
        source = query(root, "SELECT * FROM source_manifests WHERE id=?", (manifest_id,))[0]
        manifest = json.loads(source["manifest_json"])
        raw_path = Path(source["raw_path"])
        if file_hash(raw_path) != manifest["sha256"]:
            raise ValueError("Expanded-stat raw source integrity failure")
        raw = pd.read_parquet(raw_path, columns=list(FIELDS))
        raw["source_row_number"] = np.arange(1, len(raw) + 1)
        canonical = pd.read_parquet(Path(snapshot["path"]) / "team_stats.parquet")
        frame = canonical[
            [
                "game_id",
                "team_id",
                "opponent_team_id",
                "season",
                "week",
                "source_row_number",
                "sacks_suffered",
                "passing_interceptions",
            ]
        ].merge(raw, on="source_row_number", validate="one_to_one")
        for stat in FIELDS:
            values = pd.to_numeric(frame[stat], errors="raise")
            if ((values.dropna() < 0) | (values.dropna() % 1 != 0)).any():
                raise ValueError(f"Invalid team count: {stat}")
            frame[stat] = values.astype(float)
        if (frame.fg_made > frame.fg_att).any() or (frame.pat_made > frame.pat_att).any():
            raise ValueError("Made kicks exceed attempts")
        opponent = frame[["game_id", "team_id", "sacks_suffered", "passing_interceptions"]].rename(
            columns={
                "team_id": "opponent_team_id",
                "sacks_suffered": "opponent_sacks_allowed",
                "passing_interceptions": "opponent_interceptions_thrown",
            }
        )
        frame = frame.merge(opponent, on=["game_id", "opponent_team_id"], validate="one_to_one")
        disagreements = frame.def_sacks.ne(frame.opponent_sacks_allowed)
        int_disagreements = frame.def_interceptions.ne(frame.opponent_interceptions_thrown)
        audit.append(
            {
                "season": int(season),
                "team_games": len(frame),
                "nulls": {s: int(frame[s].isna().sum()) for s in FIELDS},
                "sack_credit_disagreements_excluded": int(disagreements.sum()),
                "interception_disagreements_excluded": int(int_disagreements.sum()),
                "snapshot_id": identity,
                "source_manifest_id": manifest_id,
            }
        )
        frame.loc[disagreements, "def_sacks"] = np.nan
        frame.loc[int_disagreements, "def_interceptions"] = np.nan
        frame["source_manifest_id"] = manifest_id
        records.append(frame)
    return history, pd.concat(records, ignore_index=True), lineage, audit


def forecast(actual: pd.DataFrame, games: pd.DataFrame, config: dict, method: str, *, after=None):
    context = games.loc[games.result_status.eq("final"), ["game_id", "eligible_after"]]
    historical = actual.merge(context, on="game_id", validate="many_to_one").sort_values(
        "eligible_after"
    )
    output = []
    for _, group in games.groupby(["season", "week", "cutoff"], sort=True):
        cutoff = group.cutoff.iloc[0]
        if after is not None and cutoff < pd.Timestamp(after):
            continue
        prior = historical.loc[historical.eligible_after.lt(cutoff)]
        if prior.empty:
            continue
        means = prior[list(FIELDS)].mean()
        by_team = {team: rows for team, rows in prior.groupby("team_id")}
        for game in group.itertuples():
            for team, opponent in (
                (game.home_team_id, game.away_team_id),
                (game.away_team_id, game.home_team_id),
            ):
                past = by_team.get(team, prior.iloc[:0])
                other = by_team.get(opponent, prior.iloc[:0])
                values = {stat: float(means[stat]) for stat in FIELDS}
                if method != "league":
                    for attempts, made in (("fg_att", "fg_made"), ("pat_att", "pat_made")):
                        volume = smoothed(past, attempts, float(means[attempts]), config)
                        tail = past.tail(config["history_games"])
                        league_rate = prior[made].sum() / max(1, prior[attempts].sum())
                        rate = (tail[made].sum() + config["prior_games"] * league_rate) / (
                            tail[attempts].sum() + config["prior_games"]
                        )
                        values[attempts], values[made] = volume, volume * float(np.clip(rate, 0, 1))
                    for stat, conceded in (
                        ("def_sacks", "sacks_suffered"),
                        ("def_interceptions", "passing_interceptions"),
                    ):
                        own = smoothed(past, stat, float(means[stat]), config)
                        values[stat] = own
                        if method == "opponent":
                            opponent_mean = float(prior[conceded].mean())
                            values[stat] = (
                                own + smoothed(other, conceded, opponent_mean, config)
                            ) / 2
                output.append(
                    {
                        "game_id": game.game_id,
                        "team_id": team,
                        "season": int(game.season),
                        "week": int(game.week),
                        "cutoff": cutoff,
                        "method": method,
                        **values,
                    }
                )
    return pd.DataFrame(
        output, columns=["game_id", "team_id", "season", "week", "cutoff", "method", *FIELDS]
    )


def choose(scores):
    result = {}
    for group in GROUPS:
        losses = {
            method: sum(
                s["loss_sum"] for s in scores if s["group"] == group and s["method"] == method
            )
            / max(1, sum(s["n"] for s in scores if s["group"] == group and s["method"] == method))
            for method in METHODS
        }
        result[group] = min(losses, key=losses.get)
    return result


def combine(candidates, selected):
    result = candidates["league"].copy()
    for group, method in selected.items():
        for stat in GROUPS[group]:
            result[stat] = candidates[method][stat].to_numpy()
    result["method"] = "selected"
    return result


def metrics(predictions, actual, intervals=None):
    joined = predictions.merge(
        actual[["game_id", "team_id", *FIELDS]],
        on=["game_id", "team_id"],
        suffixes=("_pred", "_actual"),
        validate="one_to_one",
    )
    reports, residuals = [], {}
    for stat in FIELDS:
        valid = joined[f"{stat}_actual"].notna() & joined[f"{stat}_pred"].notna()
        observed = joined.loc[valid, f"{stat}_actual"].to_numpy()
        predicted = joined.loc[valid, f"{stat}_pred"].to_numpy()
        error = predicted - observed
        if not len(error):
            continue
        report = {
            "stat": stat,
            "n": len(error),
            "mae": float(np.abs(error).mean()),
            "bias": float(error.mean()),
        }
        residuals[stat] = (-error).tolist()
        if intervals and stat in intervals:
            low, high = intervals[stat]
            report["coverage_80"] = float(
                ((predicted + low <= observed) & (predicted + high >= observed)).mean()
            )
        reports.append(report)
    return reports, residuals


def load(folder: Path):
    manifest = json.loads((folder / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        if file_hash(folder / name) != digest:
            raise ValueError("Expanded model integrity failure")
    return manifest


def run(features: Path, root: Path, output: Path):
    eligibility = json.loads((features / "eligibility.json").read_text())
    for name, digest in eligibility["files"].items():
        if file_hash(features / name) != digest:
            raise ValueError("Feature integrity failure")
    history, actual, lineage, audit = load_actuals(root)
    if lineage != eligibility["source_snapshots"]:
        raise ValueError("Feature and expanded target snapshots differ")
    identity = json_hash(
        {
            "features": eligibility["feature_id"],
            "sources": lineage,
            "code": file_hash(Path(__file__)),
        }
    )
    destination = output / identity
    if destination.exists():
        return load(destination)
    games = pd.read_parquet(features / "games.parquet")
    config = eligibility["config"]
    candidates = {method: forecast(actual, games, config, method) for method in METHODS}
    splits = json.loads((features / "splits.json").read_text())
    scores, reports, oof = [], [], []
    for fold in splits["folds"]:
        selected = choose(scores)
        rows = combine(candidates, selected)
        training = rows.loc[rows.game_id.isin(fold["train_game_ids"])]
        _, residuals = metrics(training, actual)
        intervals = {
            s: np.quantile(v, [0.1, 0.9]).tolist() for s, v in residuals.items() if len(v) >= 30
        }
        validation = rows.loc[rows.game_id.isin(fold["validation_game_ids"])]
        measured, _ = metrics(validation, actual, intervals)
        reports.append(
            {"season": fold["validation_season"], "selected": selected, "metrics": measured}
        )
        oof.append(validation)
        training_actual = actual.loc[actual.game_id.isin(fold["train_game_ids"])]
        scales = training_actual[list(FIELDS)].mean().clip(lower=1)
        for method, rows in candidates.items():
            joined = rows.loc[rows.game_id.isin(fold["validation_game_ids"])].merge(
                actual,
                on=["game_id", "team_id"],
                suffixes=("_pred", "_actual"),
                validate="one_to_one",
            )
            for group, stats in GROUPS.items():
                error = np.column_stack(
                    [(joined[f"{s}_pred"] - joined[f"{s}_actual"]) / scales[s] for s in stats]
                )
                scores.append(
                    {
                        "season": fold["validation_season"],
                        "group": group,
                        "method": method,
                        "loss_sum": float(np.nansum(np.abs(error))),
                        "n": int(np.isfinite(error).sum()),
                    }
                )
    selected = choose(scores)
    predictions = combine(candidates, selected)
    _, residuals = metrics(
        predictions.loc[predictions.game_id.isin(splits["final_train_game_ids"])], actual
    )
    intervals = {
        s: np.quantile(v, [0.1, 0.9]).tolist() for s, v in residuals.items() if len(v) >= 30
    }
    final, _ = metrics(
        predictions.loc[predictions.game_id.isin(splits["final_test_game_ids"])], actual, intervals
    )
    identity = json_hash(
        {
            "features": eligibility["feature_id"],
            "sources": lineage,
            "code": file_hash(Path(__file__)),
        }
    )
    destination = output / identity
    if destination.exists():
        return load(destination)
    staging = output / f".staging-{uuid4().hex}"
    staging.mkdir(parents=True)
    predictions.to_parquet(staging / "projections.parquet", index=False)
    pd.concat(oof).to_parquet(staging / "validation_predictions.parquet", index=False)
    actual.to_parquet(staging / "actuals.parquet", index=False)
    (staging / "intervals.json").write_text(json.dumps(intervals, indent=2) + "\n")
    manifest = {
        "team_model_id": identity,
        "kind": "team_kicking_limited_defense_baselines",
        "config": config,
        "selected": selected,
        "audit": audit,
        "validation": reports,
        "selection_scores": scores,
        "final_test_season": splits["final_test_season"],
        "final_test": final,
        "test_policy": "First fixed additional-target test; never retune against it.",
        "source_snapshots": lineage,
        "feature_id": eligibility["feature_id"],
        "supported_fields": list(FIELDS),
        "scope": "Team aggregates only; no individual kicker/defender or full DST fantasy",
        "position_stat_rows": {
            str(p): int(n) for p, n in history["player_stats"].position.value_counts().items()
        },
        "preseason_schedule_rows": int(history["games"].game_type.eq("PRE").sum()),
        "unsupported": [
            "Individual kicker/depth assignments",
            "Individual defenders/returners",
            "Full DST fantasy",
            "Other on-field roles",
            "Preseason",
        ],
        "historical_mode": "approximate_corrected_sources",
        "recommended_for_decisions": False,
        "files": {p.name: file_hash(p) for p in staging.iterdir()},
        "path": str(destination.resolve()),
    }
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    staging.rename(destination)
    return manifest


def infer(folder: Path, features: Path, root: Path):
    model = load(folder)
    eligibility = json.loads((features / "eligibility.json").read_text())
    if model["config"] != eligibility["config"]:
        raise ValueError("Expanded feature definition differs")
    _, actual, lineage, _ = load_actuals(root)
    if lineage != eligibility["source_snapshots"]:
        raise ValueError("Expanded input snapshots differ")
    games = pd.read_parquet(features / "games.parquet")
    after = eligibility.get("live_cutoff")
    candidates = {
        method: forecast(actual, games, model["config"], method, after=after) for method in METHODS
    }
    return combine(candidates, model["selected"]), model
