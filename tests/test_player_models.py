"""Synthetic player baselines test causality, unknowns and opportunity allocation."""

import copy

import pandas as pd
from pandas.testing import assert_frame_equal
from test_features import config
from test_features import history as history
from test_ingestion import fixtures as fixtures

from nfl_prediction.features.pipeline import build_frames
from nfl_prediction.models.players import forecast


def prepared(history):
    games, players = build_frames(history, config())
    players = players.merge(games[["game_id", "eligible_after"]], on="game_id")
    players["participated"] = pd.Series(1, index=players.index, dtype="Int8")
    return games, players


def test_future_participation_cannot_change_earlier_predictions(history):
    games, players = prepared(history)
    original = forecast(players, games, history, config())
    changed = copy.deepcopy(players)
    changed.loc[changed.season.eq(2025), "participated"] = 0
    updated = forecast(changed, games, history, config())
    assert_frame_equal(original.loc[original.season.lt(2025)], updated.loc[updated.season.lt(2025)])
    for (_, _), group in original.loc[original.support.eq("baseline_approximate")].groupby(
        ["game_id", "team_id"]
    ):
        first = group.iloc[0]
        for stat in ("attempts", "carries", "targets"):
            assert (
                abs(
                    group[f"unconditional_{stat}"].sum()
                    + first.other_opportunities[stat]
                    - first.team_volume[stat]
                )
                < 1e-8
            )
    assert (original.conditional_passing_yards.dropna() < 0).any()


def test_confirmed_out_redistributes_without_questionable_weight(history):
    games, players = prepared(history)
    chosen = players.loc[players.season.eq(2025) & players.week.eq(1)].iloc[0]
    extra = players.loc[[chosen.name]].copy()
    extra["player_id"] = "00-0000009"
    players = pd.concat([players, extra], ignore_index=True)
    normal = forecast(players, games, history, config())
    changed = players.copy()
    mask = changed.game_id.eq(chosen.game_id) & changed.player_id.eq(chosen.player_id)
    changed.loc[mask, "injury_designation"] = "Out"
    out = forecast(changed, games, history, config())
    assert (
        out.loc[
            out.game_id.eq(chosen.game_id) & out.player_id.eq(chosen.player_id),
            "unconditional_attempts",
        ].iloc[0]
        == 0
    )

    def backup(frame):
        return frame.loc[
            frame.game_id.eq(chosen.game_id) & frame.player_id.eq("00-0000009"),
            "unconditional_attempts",
        ].iloc[0]

    assert backup(out) > backup(normal)
    changed.loc[mask, "injury_designation"] = "Questionable"
    questionable = forecast(changed, games, history, config())
    assert backup(questionable) == backup(normal)


def test_unknown_participation_has_no_invented_probability(history):
    games, players = prepared(history)
    players["participated"] = pd.NA
    output = forecast(players, games, history, config())
    assert output.offense_participation_probability.isna().all()
    assert output.unconditional_attempts.isna().all()
    assert output.support.eq("unsupported_cold_start").all()


def test_missing_actual_stat_is_not_scored_as_known_zero():
    from nfl_prediction.models.players import summarize

    predicted = pd.DataFrame(
        {
            "game_id": ["synthetic-a", "synthetic-b"],
            "team_id": ["DAL", "DAL"],
            "player_id": ["00-0000001", "00-0000002"],
            "position": ["QB", "QB"],
            "conditional_attempts": [10.0, 0.0],
            "unconditional_attempts": [5.0, 0.0],
            "baseline_attempts": [5.0, 0.0],
            "baseline_carries": [0.0, 0.0],
            "baseline_targets": [0.0, 0.0],
        }
    )
    actual = pd.DataFrame(
        {
            "game_id": ["synthetic-a", "synthetic-b"],
            "team_id": ["DAL", "DAL"],
            "player_id": ["00-0000001", "00-0000002"],
            "participated": pd.Series([1, 0], dtype="Int8"),
            "attempts": [None, 0.0],
        }
    )
    reports, _ = summarize(predicted, actual, ["attempts"])
    all_reports = [r for r in reports if r["workload_bucket"] == "all"]
    assert len(all_reports) == 1
    assert all_reports[0]["mode"] == "unconditional" and all_reports[0]["n"] == 1
    assert all_reports[0]["mae"] == 0
