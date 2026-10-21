"""Fake time and source-step adapters verify refresh safety without network."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from test_features import config
from test_features import history as history
from test_ingestion import fixtures as fixtures

from nfl_prediction.features.pipeline import build_frames
from nfl_prediction.refresh import RefreshConfig, due, execute_steps, publication_eligible


def settings():
    return RefreshConfig(
        season=2026, game_model=Path("test"), player_model=Path("test"), participation=Path("test")
    )


def test_daily_and_pregame_catchup_never_schedules_fake_past_game():
    cfg = settings()
    now = datetime(2026, 10, 21, 15, tzinfo=UTC)
    assert due(cfg, now, now - timedelta(days=1), [])
    assert not due(cfg, now, now - timedelta(minutes=1), [])
    assert due(cfg, now, now - timedelta(minutes=40), [now + timedelta(minutes=20)])
    assert not due(cfg, now, now - timedelta(minutes=40), [now - timedelta(minutes=1)])
    assert not publication_eligible(
        now,
        now - timedelta(seconds=1),
        {"schedule_freshness": "observed", "roster_freshness": "observed"},
        stale_hours=36,
    )
    assert not publication_eligible(
        now,
        now + timedelta(hours=1),
        {"schedule_freshness": "stale", "roster_freshness": "observed"},
        stale_hours=36,
    )


def test_failed_source_adapter_prevents_downstream_publication():
    called, checkpoints = [], []

    def failed():
        raise OSError("synthetic offline source")

    with pytest.raises(OSError, match="offline"):
        execute_steps(
            [("sources", failed), ("publish", lambda: called.append(True))],
            {"steps": []},
            lambda report: checkpoints.append(dict(report)),
        )
    assert not called
    assert checkpoints[-1]["status"] == "failed"
    assert "finished_at" in checkpoints[-1]


def test_current_observed_roster_is_used_only_for_live_future_games(history):
    now = history["games"].kickoff_at.max() - timedelta(hours=1)
    game = history["games"].sort_values("kickoff_at").iloc[-1]
    observed = {
        "roster_freshness": "observed",
        "roster_batch_id": "synthetic-batch",
        "roster": [
            {
                "player_id": "synthetic-rookie",
                "team_id": game.home_team_id,
                "position": "QB",
                "roster_status": "ACT",
            }
        ],
        "availability": [],
    }
    games, players = build_frames(
        history, config(), observation_reader=lambda *args: observed, live_cutoff=now
    )
    current = players.loc[players.player_id.eq("synthetic-rookie")]
    assert not current.empty
    assert current.cutoff.eq(now).all()
    assert current.roster_eligibility.eq("prospective_observed_roster").all()
    assert not players.loc[players.cutoff.lt(now)].player_id.eq("synthetic-rookie").any()
    assert games.loc[games.kickoff_at.gt(now)].cutoff.eq(now).all()


def test_incompatible_feature_definition_stops_before_inference(tmp_path):
    import json

    from nfl_prediction.models.player_defaults import infer

    features, model = tmp_path / "features", tmp_path / "model"
    features.mkdir()
    model.mkdir()
    (features / "eligibility.json").write_text(json.dumps({"config": {"stats": ["wrong"]}}))
    (model / "manifest.json").write_text(
        json.dumps({"files": {}, "config": {"stats": ["attempts"]}})
    )
    with pytest.raises(ValueError, match="definition differs"):
        infer(features, tmp_path / "no-participation", tmp_path, model, tmp_path / "output")
    assert not (tmp_path / "output").exists()
