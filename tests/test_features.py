"""Tiny synthetic games verify timing and split invariants, not NFL accuracy."""

import copy
import json

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from test_ingestion import fixtures as fixtures

from nfl_prediction.data.ingest import SOURCES
from nfl_prediction.data.normalize import normalize, read_source, reconcile
from nfl_prediction.evaluation.harness import GAME_COLUMNS, preprocessor
from nfl_prediction.features.pipeline import DEFAULT_CONFIG, build_frames, split_manifest


@pytest.fixture
def history(fixtures):
    frames = {}
    for dataset, pattern in SOURCES.items():
        raw, _ = read_source(fixtures[pattern.format(season=2025)], dataset)
        frames[dataset], _, _ = normalize(raw, dataset, 2025, "synthetic")
    reconcile(frames)
    history = {}
    for name in ("games", "team_stats", "player_stats", "weekly_rosters"):
        years = []
        for year in (2023, 2024, 2025):
            frame = frames[name].copy()
            frame["season"] = year
            if "game_id" in frame:
                frame["game_id"] = frame.game_id.str.replace("2025", str(year))
            if "kickoff_at" in frame:
                frame["kickoff_at"] = frame.kickoff_at.map(lambda value: value.replace(year=year))
            years.append(frame)
        history[name] = pd.concat(years, ignore_index=True)
    return history


def config():
    return json.loads(DEFAULT_CONFIG.read_text())


def test_future_outcomes_cannot_change_earlier_features(history):
    original, original_players = build_frames(history, config())
    changed = copy.deepcopy(history)
    changed["games"].loc[changed["games"].season.eq(2025), "home_score"] = 99
    changed["player_stats"].loc[changed["player_stats"].season.eq(2025), "attempts"] = 999
    updated, updated_players = build_frames(changed, config())
    assert_frame_equal(original.loc[original.season.lt(2025)], updated.loc[updated.season.lt(2025)])
    assert_frame_equal(
        original_players.loc[original_players.season.lt(2025)],
        updated_players.loc[updated_players.season.lt(2025)],
    )
    # Current-game outcome is also excluded from that game's predictors.
    assert_frame_equal(
        original.loc[original.season.eq(2025) & original.week.eq(1), GAME_COLUMNS],
        updated.loc[updated.season.eq(2025) & updated.week.eq(1), GAME_COLUMNS],
    )


def test_shifted_player_history_and_historical_trade_context(history):
    _, players = build_frames(history, config())
    first = players.loc[players.season.eq(2023) & players.week.eq(1)]
    assert first.history_games.eq(0).all()
    assert first.lag_attempts.eq(0).all()  # Explicit cold start, no invented career.
    traded = players.loc[
        players.season.eq(2023) & players.week.eq(2) & players.player_id.eq("00-0000001")
    ].iloc[0]
    assert traded.team_id == "NYG" and traded.prior_team_id == "DAL"
    assert traded.history_games == 1
    assert traded.lag_attempts == pytest.approx(2.0)


def test_holdout_grouping_and_training_only_preprocessing(history):
    games, players = build_frames(history, config())
    splits = split_manifest(games)
    assert splits["final_test_season"] == 2025
    fold = splits["folds"][0]
    assert not set(fold["train_game_ids"]) & set(fold["validation_game_ids"])
    assert not set(fold["train_game_ids"]) & set(splits["final_test_game_ids"])
    # All player rows inherit their game's partition; there is no row random split.
    assert players.loc[players.game_id.isin(fold["train_game_ids"]), "season"].eq(2023).all()
    transform = preprocessor().fit(pd.DataFrame({"x": [1.0, 3.0]}))
    transform.transform(pd.DataFrame({"x": [999999.0]}))
    assert transform.named_steps["standardscaler"].mean_[0] == 2


def test_unfinalized_game_does_not_feed_later_features(history):
    history["games"].loc[history["games"].season.eq(2023), "result_status"] = "provisional"
    games, players = build_frames(history, config())
    assert games.loc[games.season.eq(2024) & games.week.eq(1), "home_history_games"].eq(0).all()
    assert players.loc[players.season.eq(2024) & players.week.eq(1), "history_games"].eq(0).all()
