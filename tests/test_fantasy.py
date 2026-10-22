"""Fantasy scoring/assignment invariants on explicitly synthetic joint samples."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from nfl_prediction.fantasy import Entry, Roster, Scoring, optimize, score, validate_locked_change


def entry(identity, position):
    return Entry(
        player_id=identity,
        team_id="DAL",
        game_id="synthetic",
        forecast_id="synthetic",
        position=position,
        name=identity,
    )


def test_negative_stats_and_versioned_scoring_presets():
    frame = pd.DataFrame(
        {
            "passing_yards": [250, -10],
            "passing_tds": [2, 0],
            "passing_interceptions": [1, 0],
            "rushing_yards": [-5, 0],
            "rushing_tds": [0, 0],
            "receiving_yards": [10, 0],
            "receiving_tds": [0, 0],
            "receptions": [2, 0],
        }
    )
    assert score(frame, Scoring(name="standard")).tolist() == [16.5, -0.4]
    assert score(frame, Scoring(name="half_ppr"))[0] == 17.5
    assert score(frame, Scoring(name="ppr"))[0] == 18.5
    with pytest.raises(ValueError, match="missing"):
        score(frame.drop(columns="passing_tds"), Scoring())


def test_exact_assignment_avoids_greedy_flex_error_and_duplicate_players():
    roster = Roster(
        players=[entry("rb", "RB"), entry("wr", "WR"), entry("te", "TE")],
        slots={"FLEX": ["RB", "WR", "TE"], "RB": ["RB"]},
    )
    values = {
        "rb": np.array([20.0, 20.0]),
        "wr": np.array([19.0, 19.0]),
        "te": np.array([1.0, 1.0]),
    }
    result = optimize(roster, values, locked={}, unavailable=set())
    assert result == {"RB": "rb", "FLEX": "wr"}
    with pytest.raises(ValidationError, match="Duplicate"):
        Roster(players=[entry("same", "RB"), entry("same", "WR")])
    with pytest.raises(ValidationError, match="Ineligible"):
        Roster(players=[entry("wr", "WR")], slots={"QB": ["QB"]}, lineup={"QB": "wr"})


def test_started_slots_and_bench_players_cannot_move():
    now = datetime(2026, 10, 25, 19, tzinfo=UTC)
    previous = Roster(
        players=[entry("started", "RB"), entry("bench", "RB"), entry("future", "RB")],
        slots={"RB": ["RB"]},
        lineup={"RB": "started"},
    )
    values = {
        "started": np.array([1.0, 1.0]),
        "bench": np.array([30.0, 30.0]),
        "future": np.array([20.0, 20.0]),
    }
    assert optimize(previous, values, locked={"RB": "started"}, unavailable={"bench"}) == {
        "RB": "started"
    }
    changed = previous.model_copy(update={"lineup": {"RB": "future"}})
    with pytest.raises(ValueError, match="locked"):
        validate_locked_change(
            previous,
            changed,
            {
                "started": now - timedelta(hours=1),
                "bench": now - timedelta(hours=1),
                "future": now + timedelta(hours=1),
            },
            now,
        )
    empty = previous.model_copy(update={"lineup": {}})
    with pytest.raises(ValueError, match="bench"):
        validate_locked_change(
            empty,
            previous,
            {
                "started": now - timedelta(hours=1),
                "bench": now - timedelta(hours=1),
                "future": now + timedelta(hours=1),
            },
            now,
        )


def test_risk_preference_is_explicit_and_infeasibility_is_reported():
    roster = Roster(players=[entry("safe", "WR"), entry("volatile", "WR")], slots={"WR": ["WR"]})
    values = {"safe": np.array([10.0, 10.0]), "volatile": np.array([0.0, 22.0])}
    assert optimize(roster, values, locked={}, unavailable=set())["WR"] == "volatile"
    assert optimize(roster, values, locked={}, unavailable=set(), risk="floor")["WR"] == "safe"
    with pytest.raises(ValueError, match="Not enough"):
        optimize(roster, values, locked={}, unavailable={"safe", "volatile"})


def test_local_write_boundary_rejects_remote_origin_and_missing_header(tmp_path, monkeypatch):
    from http_client import LocalClient

    from nfl_prediction.api.app import app

    monkeypatch.setenv("NFL_DATA_DIR", str(tmp_path))
    with LocalClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)) as client:
        path = "/api/fantasy/rosters/test"
        assert client.post(path, json={}).status_code == 403
        assert (
            client.post(
                path, headers={"X-NFL-Local": "1", "Origin": "https://evil.example"}, json={}
            ).status_code
            == 403
        )
        assert (
            client.post(
                path, headers={"X-NFL-Local": "1", "Origin": "http://127.0.0.1:5173"}, json={}
            ).status_code
            == 200
        )
        assert client.get(path).json()["roster"]["players"] == []
    assert not (tmp_path / "metadata.sqlite").exists()


def test_started_player_identity_cannot_be_rebound_to_future_game():
    now = datetime(2026, 10, 25, 19, tzinfo=UTC)
    original = Roster(
        players=[entry("started", "QB")], slots={"QB": ["QB"]}, lineup={"QB": "started"}
    )
    changed = Roster(
        players=[entry("started", "QB").model_copy(update={"game_id": "future"})],
        slots={"QB": ["QB"]},
        lineup={"QB": "started"},
    )
    with pytest.raises(ValueError, match="game/team/position"):
        validate_locked_change(original, changed, {"started": now - timedelta(hours=1)}, now)
