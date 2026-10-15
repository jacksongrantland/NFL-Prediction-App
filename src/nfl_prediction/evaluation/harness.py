"""Preprocessing is fitted within training folds, never on validation/test rows."""

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

GAME_COLUMNS = [
    f"{side}_{name}"
    for side in ("home", "away")
    for name in ("points", "allowed", "history_games", "rest_days")
]


def preprocessor():
    return make_pipeline(
        SimpleImputer(strategy="median", keep_empty_features=True), StandardScaler()
    )


def check_folds(path: Path) -> dict:
    start = time.perf_counter()
    games = pd.read_parquet(path / "games.parquet").set_index("game_id")
    players = pd.read_parquet(path / "players.parquet")
    splits = json.loads((path / "splits.json").read_text())
    reports = []
    for fold in splits["folds"]:
        train, val = fold["train_game_ids"], fold["validation_game_ids"]
        if set(train) & set(val) or set(train + val) & set(splits["final_test_game_ids"]):
            raise ValueError("Overlapping evaluation partitions")
        if games.loc[train, "eligible_after"].max() >= games.loc[val, "cutoff"].min():
            raise ValueError("Training labels are unavailable by validation cutoff")
        transform = preprocessor().fit(games.loc[train, GAME_COLUMNS])
        values = transform.transform(games.loc[val, GAME_COLUMNS])
        if not np.isfinite(values).all():
            raise ValueError("Nonfinite transformed features")
        reports.append(
            {
                "validation_season": fold["validation_season"],
                "train_games": len(train),
                "validation_games": len(val),
                "train_player_rows": int(players.game_id.isin(train).sum()),
                "validation_player_rows": int(players.game_id.isin(val).sum()),
                "training_feature_means": transform.named_steps["standardscaler"].mean_.tolist(),
            }
        )
    report = {
        "folds": reports,
        "final_test_season": splits["final_test_season"],
        "final_test_not_evaluated": True,
        "elapsed_seconds": round(time.perf_counter() - start, 3),
    }
    (path / "harness.json").write_text(json.dumps(report, indent=2) + "\n")
    return report
