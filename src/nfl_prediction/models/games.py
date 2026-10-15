"""Small CPU game models selected on earlier seasons; ties remain a third outcome."""

import json
import platform
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import log_loss
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import make_pipeline

from nfl_prediction.data.downloads import file_hash
from nfl_prediction.data.ingest import json_hash
from nfl_prediction.evaluation.harness import GAME_COLUMNS, preprocessor

SEED = 2026
KINDS = ("league", "rolling", "linear", "tree")


def fit(games: pd.DataFrame, kind: str) -> dict:
    margin = (games.home_score - games.away_score).astype(float)
    regular = games.game_type.eq("REG")
    tie_rate = (int((margin.eq(0) & regular).sum()) + 0.5) / (int(regular.sum()) + 100)
    model = {
        "kind": kind,
        "tie_rate": tie_rate,
        "home_edge": float(margin.mean()),
        "points": float((games.home_score.mean() + games.away_score.mean()) / 2),
        "margin_scale": max(float(margin.std()), 1.0),
    }
    if kind in ("linear", "tree"):
        decided = margin.ne(0)
        classifier = (
            LogisticRegression(C=1, max_iter=1000, random_state=SEED)
            if kind == "linear"
            else HistGradientBoostingClassifier(
                max_iter=60, max_leaf_nodes=7, l2_regularization=10, random_state=SEED
            )
        )
        regressor = (
            Ridge(alpha=10)
            if kind == "linear"
            else MultiOutputRegressor(
                HistGradientBoostingRegressor(
                    max_iter=60, max_leaf_nodes=7, l2_regularization=10, random_state=SEED
                )
            )
        )
        model["classifier"] = make_pipeline(preprocessor(), classifier).fit(
            games.loc[decided, GAME_COLUMNS], margin.loc[decided].gt(0).astype(int)
        )
        model["scores"] = make_pipeline(preprocessor(), regressor).fit(
            games[GAME_COLUMNS], games[["home_score", "away_score"]].astype(float)
        )
    return model


def predict(model: dict, games: pd.DataFrame) -> pd.DataFrame:
    if model["kind"] == "league":
        home = np.full(len(games), model["points"] + model["home_edge"] / 2)
        away = np.full(len(games), model["points"] - model["home_edge"] / 2)
    elif model["kind"] == "rolling":
        home = (games.home_points.to_numpy() + games.away_allowed.to_numpy()) / 2 + model[
            "home_edge"
        ] / 2
        away = (games.away_points.to_numpy() + games.home_allowed.to_numpy()) / 2 - model[
            "home_edge"
        ] / 2
    else:
        home, away = model["scores"].predict(games[GAME_COLUMNS]).T
    home, away = np.maximum(home, 0), np.maximum(away, 0)
    if model["kind"] in ("linear", "tree"):
        q = model["classifier"].predict_proba(games[GAME_COLUMNS])[:, 1]
    else:
        q = 1 / (1 + np.exp(-(home - away) * 1.7 / model["margin_scale"]))
    tie = np.where(games.game_type.eq("REG"), model["tie_rate"], 0.0)
    return pd.DataFrame(
        {
            "game_id": games.game_id.to_numpy(),
            "home_expected": home,
            "away_expected": away,
            "home_win": (1 - tie) * q,
            "tie": tie,
            "away_win": (1 - tie) * (1 - q),
        }
    )


def metrics(actual: pd.DataFrame, predicted: pd.DataFrame) -> dict:
    margin = (actual.home_score - actual.away_score).to_numpy(dtype=float)
    outcome = np.where(margin > 0, 0, np.where(margin == 0, 1, 2))
    probabilities = predicted[["home_win", "tie", "away_win"]].to_numpy()
    target = np.eye(3)[outcome]
    error = (predicted.home_expected - predicted.away_expected).to_numpy() - margin
    score_error = predicted[["home_expected", "away_expected"]].to_numpy() - actual[
        ["home_score", "away_score"]
    ].to_numpy(dtype=float)
    bins = []
    for low in np.arange(0, 1, 0.1):
        mask = (probabilities[:, 0] >= low) & (probabilities[:, 0] < low + 0.1)
        if mask.any():
            bins.append(
                {
                    "low": round(float(low), 1),
                    "n": int(mask.sum()),
                    "predicted": float(probabilities[mask, 0].mean()),
                    "observed_home_win": float((outcome[mask] == 0).mean()),
                }
            )
    return {
        "n": len(actual),
        "ties": int((outcome == 1).sum()),
        "log_loss": float(log_loss(outcome, probabilities, labels=[0, 1, 2])),
        "brier_multiclass": float(np.mean(np.sum((probabilities - target) ** 2, axis=1))),
        "accuracy": float(np.mean(probabilities.argmax(axis=1) == outcome)),
        "margin_mae": float(np.mean(np.abs(error))),
        "margin_rmse": float(np.sqrt(np.mean(error**2))),
        "score_mae": float(np.mean(np.abs(score_error))),
        "score_rmse": float(np.sqrt(np.mean(score_error**2))),
        "calibration": bins,
    }


def train(feature_path: Path, output: Path) -> dict:
    start = time.perf_counter()
    eligibility = json.loads((feature_path / "eligibility.json").read_text())
    for name, checksum in eligibility["files"].items():
        if file_hash(feature_path / name) != checksum:
            raise ValueError("Feature artifact integrity failure")
    games = pd.read_parquet(feature_path / "games.parquet").set_index("game_id", drop=False)
    splits = json.loads((feature_path / "splits.json").read_text())
    validation = {}
    oof = {}
    for kind in KINDS:
        predictions, actuals = [], []
        for fold in splits["folds"]:
            training = games.loc[fold["train_game_ids"]].reset_index(drop=True)
            actual = games.loc[fold["validation_game_ids"]].reset_index(drop=True)
            predictions.append(predict(fit(training, kind), actual))
            actuals.append(actual)
        actual = pd.concat(actuals, ignore_index=True)
        prediction = pd.concat(predictions, ignore_index=True)
        validation[kind] = metrics(actual, prediction)
        oof[kind] = prediction.assign(
            season=actual.season.to_numpy(),
            week=actual.week.to_numpy(),
            actual_home=actual.home_score.to_numpy(),
            actual_away=actual.away_score.to_numpy(),
        )
    # Prefer simpler models when predictive log loss differs by <= 0.005.
    best = min(value["log_loss"] for value in validation.values())
    selected = next(kind for kind in KINDS if validation[kind]["log_loss"] <= best + 0.005)
    training = games.loc[splits["final_train_game_ids"]].reset_index(drop=True)
    model = fit(training, selected)
    identity = json_hash(
        {
            "features": eligibility["feature_id"],
            "selected": selected,
            "code": file_hash(Path(__file__)),
            "seed": SEED,
        }
    )
    destination = output / identity
    if destination.exists():
        return load(destination)[1]
    folder = output / f".staging-{uuid4().hex}"
    folder.mkdir(parents=True)
    joblib.dump(model, folder / "model.joblib")
    oof[selected].to_parquet(folder / "validation_predictions.parquet", index=False)
    residuals = oof[selected]
    residuals.assign(
        home_residual=residuals.actual_home - residuals.home_expected,
        away_residual=residuals.actual_away - residuals.away_expected,
    ).to_parquet(folder / "residuals.parquet", index=False)
    report = {
        "model_id": identity,
        "selected": selected,
        "promotion_status": "candidate",
        "seed": SEED,
        "feature_id": eligibility["feature_id"],
        "feature_path": str(feature_path.resolve()),
        "feature_columns": GAME_COLUMNS,
        "config": eligibility["config"],
        "model_config": {
            "logistic_C": 1,
            "ridge_alpha": 10,
            "tree_iterations": 60,
            "tree_leaf_nodes": 7,
            "tree_l2": 10,
            "selection_log_loss_tolerance": 0.005,
        },
        "feature_file_hashes": eligibility["files"],
        "training_cutoff": training.eligible_after.max().isoformat(),
        "source_snapshots": eligibility["source_snapshots"],
        "validation": validation,
        "final_test_season": splits["final_test_season"],
        "test_evaluated": False,
        "dependencies": {
            "python": platform.python_version(),
            "sklearn": sklearn.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "calibration_policy": "earlier validation reliability bins; no test-fitted calibration",
        "tie_policy": "three outcomes; smoothed training regular-season tie rate; no playoff ties",
        "historical_mode": eligibility["historical_mode"],
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "artifact_hashes": {p.name: file_hash(p) for p in folder.iterdir()},
        "path": str(destination.resolve()),
    }
    (folder / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    folder.rename(destination)
    return report


def load(folder: Path) -> tuple[dict, dict]:
    manifest = json.loads((folder / "manifest.json").read_text())
    for name, checksum in manifest["artifact_hashes"].items():
        if file_hash(folder / name) != checksum:
            raise ValueError("Model artifact integrity failure")
    # Only load trusted local artifacts created by this CLI; pickle is not a download format.
    return joblib.load(folder / "model.joblib"), manifest


def evaluate(folder: Path) -> dict:
    model, manifest = load(folder)
    result_path = folder / "final_test.json"
    if result_path.exists():
        return json.loads(result_path.read_text())
    features = Path(manifest["feature_path"])
    for name, checksum in manifest["feature_file_hashes"].items():
        if file_hash(features / name) != checksum:
            raise ValueError("Evaluation feature artifact integrity failure")
    splits = json.loads((features / "splits.json").read_text())
    all_games = pd.read_parquet(features / "games.parquet").set_index("game_id", drop=False)
    actual = all_games.loc[splits["final_test_game_ids"]].reset_index(drop=True)
    predicted = predict(model, actual)
    report = metrics(actual, predicted)
    # Seeded complete-week bootstrap: both teams stay in their game, games in week.
    losses = np.abs(
        (predicted.home_expected - predicted.away_expected).to_numpy()
        - (actual.home_score - actual.away_score).to_numpy(dtype=float)
    )
    week_losses = (
        pd.DataFrame({"week": actual.week, "loss": losses})
        .groupby("week")
        .loss.agg(["sum", "count"])
    )
    rng = np.random.default_rng(SEED)
    samples = week_losses.to_numpy()[
        rng.integers(0, len(week_losses), size=(500, len(week_losses)))
    ]
    bootstrap = samples[:, :, 0].sum(axis=1) / samples[:, :, 1].sum(axis=1)
    report.update(
        model_id=manifest["model_id"],
        season=manifest["final_test_season"],
        historical_mode=manifest["historical_mode"],
        margin_mae_week_bootstrap_95=np.quantile(bootstrap, [0.025, 0.975]).tolist(),
        evaluated_at=datetime.now(UTC).isoformat(),
        policy="Final test recorded once; reruns return saved result. Do not tune against it.",
    )
    with result_path.open("x") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    manifest["test_evaluated"] = True
    manifest["artifact_hashes"]["final_test.json"] = file_hash(result_path)
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return report


def scheduled(folder: Path, feature_path: Path) -> list[dict]:
    model, manifest = load(folder)
    eligibility = json.loads((feature_path / "eligibility.json").read_text())
    if eligibility["config"] != manifest["config"]:
        raise ValueError("Feature definition differs from trained model")
    games = pd.read_parquet(feature_path / "games.parquet")
    games = games.loc[
        games.kickoff_at.gt(datetime.now(UTC)) & games.game_type.isin(["REG", "POST"])
    ].reset_index(drop=True)
    if games.empty:
        return []
    return json.loads(
        predict(model, games)
        .assign(model_id=manifest["model_id"], forecast_type="unpublished_preview")
        .to_json(orient="records")
    )


def promote(folder: Path) -> dict:
    _, manifest = load(folder)
    if not manifest["test_evaluated"]:
        raise ValueError("Record the selected model's final evaluation before promotion")
    manifest["promotion_status"] = "promoted_local"
    manifest["promoted_at"] = datetime.now(UTC).isoformat()
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest
