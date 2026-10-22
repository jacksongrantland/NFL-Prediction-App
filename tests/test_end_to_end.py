"""Generated fixtures exercise the complete local flow; never real prediction history."""

from datetime import timedelta

import pandas as pd
from http_client import LocalClient
from test_features import config
from test_features import history as history
from test_ingestion import fake_downloader
from test_ingestion import fixtures as fixtures

from nfl_prediction.api.app import app
from nfl_prediction.data.downloads import file_hash
from nfl_prediction.data.ingest import run_ingestion
from nfl_prediction.fantasy import Entry, Roster, Scoring, recommend, save
from nfl_prediction.features.pipeline import build_frames
from nfl_prediction.models.games import fit, predict
from nfl_prediction.models.players import forecast
from nfl_prediction.models.simulation import simulate, validate
from nfl_prediction.paper import Line, PaperStore, account
from nfl_prediction.refresh import atomic_json
from nfl_prediction.storage.forecasts import ForecastStore


def test_generated_local_flow_from_ingestion_to_corrected_paper_actual(
    tmp_path, fixtures, history, monkeypatch
):
    root, artifacts = tmp_path / "data", tmp_path / "artifacts"
    ingested = run_ingestion(
        [2025], root, current_season=2026, downloader_factory=fake_downloader(fixtures)
    )
    kickoff = (
        history["games"].loc[history["games"].game_id.eq("2025_01_DAL_PHI"), "kickoff_at"].iloc[0]
    )
    clock = [kickoff - timedelta(hours=1)]
    games, players = build_frames(history, config(), live_cutoff=clock[0])
    players = players.merge(games[["game_id", "eligible_after"]], on="game_id")
    players["participated"] = pd.Series(
        1, index=players.index, dtype="Int8"
    )  # synthetic labels only
    projections = forecast(players, games, history, {**config(), "allocation": "lag_reference"})
    target = games.loc[games.game_id.eq("2025_01_DAL_PHI")].copy()
    trained = fit(games.loc[games.eligible_after.lt(clock[0])], "league")
    estimate = predict(trained, target.reset_index(drop=True))
    game = target.iloc[0].to_dict()
    game.update(
        home_expected=float(estimate.home_expected.iloc[0]),
        away_expected=float(estimate.away_expected.iloc[0]),
    )
    result = simulate(
        game, projections.loc[projections.game_id.eq(game["game_id"])], count=100, seed=41
    )
    validate(result)
    folder = artifacts / "synthetic-joint"
    folder.mkdir(parents=True)
    result["players"].assign(game_id=game["game_id"]).to_parquet(
        folder / "player_draws.parquet", index=False
    )
    result["teams"].assign(game_id=game["game_id"]).to_parquet(
        folder / "team_draws.parquet", index=False
    )
    atomic_json(
        folder / "manifest.json",
        {
            "simulation_id": "synthetic-e2e",
            "files": {p.name: file_hash(p) for p in folder.iterdir()},
        },
    )
    forecasts = ForecastStore(root, clock=lambda: clock[0])
    paper = PaperStore(root, clock=lambda: clock[0])
    try:
        version = forecasts.publish(
            {
                "game_id": game["game_id"],
                "cutoff": clock[0].isoformat(),
                "kickoff_at": kickoff.isoformat(),
                "source_snapshots": {"synthetic": ingested["seasons"][0]["snapshot_id"]},
                "input_freshness": {"mode": "generated_test_fixture"},
                "model_versions": {"game": "synthetic-league"},
                "simulation_seed": 41,
                "simulation_config": {
                    "count": 100,
                    "simulation_id": "synthetic-e2e",
                    "artifact_path": str(folder.resolve()),
                },
                "supported_outputs": ["synthetic-test-only"],
                "summary": result["summary"],
            }
        )
        roster = Roster(
            players=[
                Entry(
                    player_id="00-0000001",
                    team_id="DAL",
                    game_id=game["game_id"],
                    forecast_id=version,
                    position="QB",
                    name="Synthetic fixture",
                )
            ],
            slots={"QB": ["QB"]},
        )
        save(root, "synthetic-roster", roster, now=clock[0])
        lineup = recommend(root, artifacts, roster, Scoring(), now=clock[0])
        assert lineup["recommended"]["lineup"] == {"QB": "00-0000001"}
        paper.initialize("synthetic-e2e", 10000)
        line = paper.line(
            Line(forecast_id=version, market="moneyline", selection="home", odds="+100")
        )
        entry = paper.enter("synthetic-e2e", version, line["id"], 1000, "single-submission")
        clock[0] = kickoff + timedelta(hours=6)
        assert forecasts.lock(game["game_id"])["forecast_id"] == version
        forecasts.result(
            game["game_id"],
            {"home_score": 24, "away_score": 20},
            status="settled",
            source_revision="generated-result-1",
        )
        assert paper.settle(entry["id"])["return_minor"] == 2000
        assert account(root, "synthetic-e2e")["balance_minor"] == 11000
        forecasts.result(
            game["game_id"],
            {"home_score": 17, "away_score": 20},
            status="settled",
            source_revision="generated-correction-2",
        )
        assert paper.settle(entry["id"])["adjustment_minor"] == -2000
        assert account(root, "synthetic-e2e")["balance_minor"] == 9000
        monkeypatch.setenv("NFL_DATA_DIR", str(root))
        with LocalClient(app) as client:
            audit = client.get("/api/games/" + game["game_id"]).json()
            assert audit["official_forecast_id"] == version and len(audit["errors"]) == 2
            assert client.get("/api/paper/accounts/synthetic-e2e").json()["settled_count"] == 1
    finally:
        forecasts.close()
        paper.close()
