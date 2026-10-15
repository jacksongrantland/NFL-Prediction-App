"""Synthetic snap coverage tests; absent and unknown must remain distinct."""

import pandas as pd
import pytest

from nfl_prediction.data.participation import labels, normalize_snaps


def sources():
    game = "2025_01_DAL_PHI"
    raw = pd.DataFrame(
        [
            {
                "game_id": game,
                "season": 2025,
                "team": "DAL",
                "pfr_player_id": f"synthetic-{i}",
                "offense_snaps": 50,
                "offense_pct": 1.0,
                "position": "QB" if i == 0 else "T",
            }
            for i in range(11)
        ]
    )
    history = {
        "weekly_rosters": pd.DataFrame(
            {"season": [2025], "source_pfr_id": ["synthetic-0"], "player_id": ["00-0000001"]}
        ),
        "games": pd.DataFrame(
            {
                "season": [2025],
                "game_id": [game],
                "result_status": ["final"],
                "home_team_id": ["PHI"],
                "away_team_id": ["DAL"],
            }
        ),
        "player_stats": pd.DataFrame(
            {
                "season": [2025],
                "game_id": [game],
                "team_id": ["DAL"],
                "player_id": ["00-0000001"],
                "attempts": [20],
                "carries": [0],
                "targets": [0],
            }
        ),
    }
    players = pd.DataFrame(
        {
            "game_id": [game, game],
            "team_id": ["DAL", "DAL"],
            "player_id": ["00-0000001", "00-0000002"],
        }
    )
    return raw, history, players


def test_absence_is_zero_only_when_team_denominator_checks_pass():
    raw, history, players = sources()
    normalized, report = normalize_snaps(raw, history, 2025)
    assert report["verified_team_games"] == 1
    assert labels(players, normalized).tolist() == [1, 0]
    incomplete, _ = normalize_snaps(raw.iloc[:-1], history, 2025)
    result = labels(players, incomplete)
    assert result.iloc[0] == 1 and pd.isna(result.iloc[1])


def test_ambiguous_mapping_and_positive_stats_prevent_zero_fill():
    raw, history, players = sources()
    history["weekly_rosters"] = pd.concat(
        [history["weekly_rosters"], history["weekly_rosters"].assign(player_id="00-0000009")]
    )
    normalized, report = normalize_snaps(raw, history, 2025)
    assert report["verified_team_games"] == 0
    assert labels(players, normalized).isna().all()


def test_negative_and_duplicate_snap_rows_fail_validation():
    raw, history, _ = sources()
    with pytest.raises(ValueError, match="Duplicate"):
        normalize_snaps(pd.concat([raw, raw.iloc[:1]]), history, 2025)
    raw.loc[0, "offense_snaps"] = -1
    with pytest.raises(ValueError, match="Invalid"):
        normalize_snaps(raw, history, 2025)
