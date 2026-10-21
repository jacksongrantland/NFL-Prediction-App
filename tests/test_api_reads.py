"""Read API pagination, history identity, empty states and no request-side writes."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from test_ingestion import fake_downloader
from test_ingestion import fixtures as fixtures

from nfl_prediction.api.app import app
from nfl_prediction.data.ingest import run_ingestion
from nfl_prediction.storage.forecasts import ForecastStore


def test_empty_api_never_creates_database(tmp_path, monkeypatch):
    root = tmp_path / "missing"
    monkeypatch.setenv("NFL_DATA_DIR", str(root))
    with TestClient(app) as client:
        assert client.get("/api/games").json()["items"] == []
        assert client.get("/api/freshness").json()["last_refresh"] is None
        assert client.get("/api/forecasts/missing").status_code == 404
        assert client.post("/api/games", json={}).status_code == 403
        assert client.get("/api/games?limit=1000").status_code == 422
    assert not root.exists()


def test_real_contract_with_synthetic_fixture_is_paginated_and_filtered(
    tmp_path, monkeypatch, fixtures
):
    root = tmp_path / "data"
    run_ingestion([2025], root, current_season=2026, downloader_factory=fake_downloader(fixtures))
    monkeypatch.setenv("NFL_DATA_DIR", str(root))
    now = datetime(2025, 9, 1, tzinfo=UTC)
    store = ForecastStore(root, clock=lambda: now)
    payload = {
        "game_id": "2025_01_DAL_PHI",
        "cutoff": now.isoformat(),
        "kickoff_at": (now + timedelta(days=1)).isoformat(),
        "source_snapshots": {"test": "synthetic"},
        "input_freshness": {"status": "synthetic"},
        "model_versions": {"game": "synthetic"},
        "simulation_seed": 1,
        "simulation_config": {"count": 100},
        "supported_outputs": ["scores"],
        "summary": {"home_expected": 20, "away_expected": 10, "player_summaries": []},
    }
    identity = store.publish(payload)
    store.close()
    with TestClient(app) as client:
        result = client.get("/api/games?season=2025&limit=1").json()
        assert result["total"] == 2 and len(result["items"]) == 1
        assert client.get("/api/games?season=2025&team=NYG").json()["total"] == 1
        detail = client.get("/api/games/2025_01_DAL_PHI").json()
        assert detail["versions"][0]["id"] == identity
        assert detail["official_forecast_id"] is None
        assert client.get(f"/api/forecasts/{identity}/players").json()["items"] == []
        assert client.get("/api/games/2025_01_DAL_PHI/versions?limit=1").json()["total"] == 1
