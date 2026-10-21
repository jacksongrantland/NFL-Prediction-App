"""Synthetic seeded joint invariants, not evidence of real-world calibration."""

import pandas as pd
from pandas.testing import assert_frame_equal

from nfl_prediction.models.simulation import simulate, validate


def inputs():
    rows = []
    for team in ("DAL", "NYG"):
        for player, position in (("quarterback", "QB"), ("receiver", "WR"), ("runner", "RB")):
            rows.append(
                {
                    "player_id": player,
                    "team_id": team,
                    "position": position,
                    "offense_participation_probability": 0.9,
                    "team_volume": {"attempts": 30, "carries": 25, "targets": 28},
                    "other_opportunities": {"attempts": 1, "carries": 2, "targets": 2},
                    "conditional_attempts": 30 if position == "QB" else 0,
                    "conditional_carries": 20 if position == "RB" else 1,
                    "conditional_targets": 10 if position == "WR" else 1,
                    "conditional_receptions": 7 if position == "WR" else 1,
                    "unconditional_targets": 9 if position == "WR" else 0.9,
                    "unconditional_receptions": 6.3 if position == "WR" else 0.9,
                    "conditional_receiving_yards": -5 if position == "RB" else 70,
                    "conditional_rushing_yards": -5 if position == "QB" else 80,
                }
            )
    return {
        "game_id": "synthetic",
        "home_team_id": "DAL",
        "away_team_id": "NYG",
        "home_expected": 24,
        "away_expected": 20,
        "game_type": "POST",
    }, pd.DataFrame(rows)


def test_joint_invariants_and_seed():
    game, players = inputs()
    result = simulate(game, players, count=100, seed=7)
    assert_frame_equal(result["players"], simulate(game, players, count=100, seed=7)["players"])
    validate(result)
    totals = result["players"].groupby(["draw", "team_id"]).sum(numeric_only=True)
    teams = result["teams"].set_index(["draw", "team_id"]).sort_index()
    assert (totals.completions <= totals.attempts).all()
    assert (totals.targets <= totals.attempts).all()
    assert (totals.receptions == totals.completions).all()
    assert (totals.receiving_yards == totals.passing_yards).all()
    assert (totals.receiving_tds == totals.passing_tds).all()
    assert (totals.receiving_tds <= totals.receptions).all()
    assert (totals.rushing_tds <= totals.carries).all()
    assert (totals.passing_interceptions <= totals.attempts - totals.completions).all()
    assert (teams.net_passing_yards == totals.passing_yards - teams.sack_yards).all()
    points = (
        6 * (totals.passing_tds + totals.rushing_tds + teams.defense_st_tds)
        + teams.extra_points
        + 2 * teams.two_point_made
        + 3 * teams.field_goals
        + 2 * teams.safeties
    )
    assert (points == teams.score).all()
    scores = teams.reset_index().pivot(index="draw", columns="side", values="score")
    assert (scores.home != scores.away).all()
    assert abs(sum(result["summary"][k] for k in ("home_win", "tie", "away_win")) - 1) < 1e-9
    sacks = teams.reset_index().pivot(index="draw", columns="side", values="sacks_allowed")
    defense = teams.reset_index().pivot(index="draw", columns="side", values="defensive_sacks")
    assert (sacks.home == defense.away).all()
    assert (sacks.away == defense.home).all()


def test_out_players_receive_no_work():
    game, players = inputs()
    players.loc[players.player_id.eq("receiver"), "offense_participation_probability"] = 0
    result = simulate(game, players, count=100)
    rows = result["players"].loc[result["players"].player_id.eq("receiver")]
    assert rows[["targets", "receptions", "receiving_yards"]].eq(0).all().all()


def test_broken_accounting_rejected():
    import pytest

    game, players = inputs()
    result = simulate(game, players, count=100)
    result["teams"].loc[0, "score"] += 1
    with pytest.raises(ValueError, match="accounting"):
        validate(result)
