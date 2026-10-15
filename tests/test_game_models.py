"""Seeded synthetic games test model contracts, not predictive NFL performance."""

import numpy as np
import pandas as pd
import pytest

from nfl_prediction.evaluation.harness import GAME_COLUMNS
from nfl_prediction.models.games import fit, metrics, predict


def synthetic_games():
    rng = np.random.default_rng(7)
    games = pd.DataFrame(rng.normal(20, 5, (80, len(GAME_COLUMNS))), columns=GAME_COLUMNS)
    games["game_id"] = [f"synthetic-{i}" for i in range(80)]
    games["game_type"] = "REG"
    games["home_score"] = rng.poisson(24, 80)
    games["away_score"] = rng.poisson(21, 80)
    return games


@pytest.mark.parametrize("kind", ["league", "rolling", "linear", "tree"])
def test_outcome_probabilities_and_playoff_tie_policy(kind):
    games = synthetic_games()
    model = fit(games.iloc[:60], kind)
    validation = games.iloc[60:].copy()
    validation.loc[validation.index[-1], "game_type"] = "POST"
    predicted = predict(model, validation)
    assert np.allclose(predicted[["home_win", "tie", "away_win"]].sum(axis=1), 1)
    assert predicted.tie.iloc[-1] == 0
    assert predicted.tie.iloc[0] > 0
    assert (predicted[["home_expected", "away_expected"]] >= 0).all().all()
    report = metrics(validation.reset_index(drop=True), predicted)
    assert report["n"] == 20
    assert np.isfinite(report["log_loss"])


def test_ties_are_not_counted_as_decisive_losses():
    actual = pd.DataFrame({"home_score": [20], "away_score": [20]})
    predicted = pd.DataFrame(
        {
            "home_win": [0.1],
            "tie": [0.8],
            "away_win": [0.1],
            "home_expected": [20],
            "away_expected": [20],
        }
    )
    report = metrics(actual, predicted)
    assert report["accuracy"] == 1
    assert report["ties"] == 1
    assert report["log_loss"] == pytest.approx(-np.log(0.8))


def test_training_never_fits_holdout_and_evaluation_is_saved_once(tmp_path, monkeypatch):
    import json
    from pathlib import Path

    from nfl_prediction.data.downloads import file_hash
    from nfl_prediction.models import games as game_models

    features = tmp_path / "features"
    features.mkdir()
    data = synthetic_games()
    data["season"] = np.repeat([2022, 2023, 2024, 2025], 20)
    data["week"] = np.tile(np.arange(1, 21), 4)
    data["cutoff"] = pd.to_datetime(data.season.astype(str) + "-09-01", utc=True)
    data["eligible_after"] = data.cutoff + pd.Timedelta(hours=12)
    data.to_parquet(features / "games.parquet", index=False)
    splits = {
        "folds": [
            {
                "train_game_ids": data.game_id.iloc[:40].tolist(),
                "validation_game_ids": data.game_id.iloc[40:60].tolist(),
            }
        ],
        "final_train_game_ids": data.game_id.iloc[:60].tolist(),
        "final_test_game_ids": data.game_id.iloc[60:].tolist(),
        "final_test_season": 2025,
    }
    (features / "splits.json").write_text(json.dumps(splits))
    (features / "eligibility.json").write_text(
        json.dumps(
            {
                "feature_id": "synthetic",
                "config": {},
                "source_snapshots": {},
                "historical_mode": "synthetic_test_fixture",
                "files": {
                    name: file_hash(features / name) for name in ("games.parquet", "splits.json")
                },
            }
        )
    )
    original_fit = game_models.fit
    fitted_ids = []

    def spy(frame, kind):
        fitted_ids.extend(frame.game_id.tolist())
        return original_fit(frame, kind)

    monkeypatch.setattr(game_models, "fit", spy)
    report = game_models.train(features, tmp_path / "models")
    assert not set(fitted_ids) & set(splits["final_test_game_ids"])
    folder = Path(report["path"])
    with pytest.raises(ValueError, match="final evaluation"):
        game_models.promote(folder)
    first = game_models.evaluate(folder)
    assert first == game_models.evaluate(folder)
    assert first["n"] == 20
    assert game_models.promote(folder)["promotion_status"] == "promoted_local"
    (folder / "model.joblib").write_bytes(b"corrupt synthetic artifact")
    with pytest.raises(ValueError, match="integrity"):
        game_models.load(folder)
