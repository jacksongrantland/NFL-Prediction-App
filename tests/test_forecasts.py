"""Fake-clock tests of immutable pregame eligibility and corrected actuals."""

from datetime import UTC, datetime, timedelta

import pytest

from nfl_prediction.storage.forecasts import ForecastStore


def fixture(tmp_path):
    clock = [datetime(2026, 10, 25, 16, tzinfo=UTC)]
    store = ForecastStore(tmp_path, clock=lambda: clock[0])
    kickoff = clock[0] + timedelta(hours=1)
    payload = {
        "game_id": "synthetic",
        "cutoff": clock[0].isoformat(),
        "kickoff_at": kickoff.isoformat(),
        "source_snapshots": {"synthetic": "test"},
        "input_freshness": {"status": "synthetic"},
        "model_versions": {"game": "test"},
        "simulation_seed": 7,
        "simulation_config": {"count": 100},
        "supported_outputs": ["scores"],
        "summary": {"home_expected": 24, "away_expected": 20},
    }
    return store, clock, payload


def test_late_job_locks_eligible_version_and_retains_corrections(tmp_path):
    store, clock, payload = fixture(tmp_path)
    try:
        identity = store.publish(payload)
        assert store.publish(payload) == identity
        clock[0] += timedelta(hours=2)
        with pytest.raises(ValueError, match="late"):
            store.publish(payload)
        locked = store.lock("synthetic")
        assert locked["forecast_id"] == identity
        assert store.lock("synthetic")["forecast_id"] == identity
        a = store.result(
            "synthetic",
            {"home_score": 21, "away_score": 20},
            status="provisional",
            source_revision="a",
        )
        b = store.result(
            "synthetic", {"home_score": 24, "away_score": 20}, status="settled", source_revision="b"
        )
        assert a != b
        assert store.audit("synthetic")["errors"][-1]["home_error"] == 0
    finally:
        store.close()


def test_missing_forecast_never_fills_after_start(tmp_path):
    store, clock, payload = fixture(tmp_path)
    try:
        store.schedule("synthetic", payload["kickoff_at"])
        clock[0] += timedelta(hours=2)
        assert store.lock("synthetic")["forecast_id"] is None
        store.schedule("synthetic", clock[0] + timedelta(days=1))
        assert store.lock("synthetic")["forecast_id"] is None
    finally:
        store.close()


def test_postponement_requires_new_kickoff_version_before_new_cutoff(tmp_path):
    store, clock, payload = fixture(tmp_path)
    try:
        original = store.publish(payload)
        delayed = {**payload, "kickoff_at": (clock[0] + timedelta(days=1)).isoformat()}
        new = store.publish(delayed)
        clock[0] += timedelta(days=1)
        assert store.lock("synthetic")["forecast_id"] == new != original
    finally:
        store.close()


def test_backdating_and_timezone_naivety_rejected(tmp_path):
    store, _, payload = fixture(tmp_path)
    try:
        with pytest.raises(ValueError, match="backdating"):
            store.publish({**payload, "generated_at": "2020-01-01T00:00:00Z"})
        with pytest.raises(ValueError, match="Timezone"):
            store.publish({**payload, "cutoff": "2026-10-25T16:00:00"})
        payload["kickoff_at"] = "2026-10-25T12:00:00-05:00"
        store.publish(payload)
    finally:
        store.close()


def test_late_reschedule_cannot_substitute_new_version(tmp_path):
    store, clock, payload = fixture(tmp_path)
    try:
        original = store.publish(payload)
        clock[0] += timedelta(hours=2)
        store.schedule("synthetic", clock[0] + timedelta(days=1))
        assert store.lock("synthetic")["forecast_id"] == original
    finally:
        store.close()


def test_history_tables_reject_mutation_and_retrospective_never_locks(tmp_path):
    from sqlalchemy.exc import IntegrityError

    store, clock, payload = fixture(tmp_path)
    try:
        store.publish(payload, retrospective=True)
        store.schedule("synthetic", payload["kickoff_at"])
        clock[0] += timedelta(hours=2)
        assert store.lock("synthetic")["forecast_id"] is None
        with pytest.raises(IntegrityError, match="immutable"):
            store.db.execute("DELETE FROM forecast_versions")
        with pytest.raises(ValueError, match="locked"):
            store.publish({**payload, "kickoff_at": (clock[0] + timedelta(days=1)).isoformat()})
    finally:
        store.close()


def test_locked_reschedule_keeps_audit_but_is_not_scored_as_new_game(tmp_path):
    store, clock, payload = fixture(tmp_path)
    try:
        version = store.publish(payload)
        clock[0] += timedelta(minutes=55)
        assert store.lock("synthetic")["forecast_id"] == version
        clock[0] += timedelta(minutes=1)
        store.schedule("synthetic", clock[0] + timedelta(days=1))
        store.result(
            "synthetic",
            {"home_score": 21, "away_score": 17},
            status="settled",
            source_revision="rescheduled-final",
        )
        audit = store.audit("synthetic")
        assert audit["eligibility_status"] == "rescheduled_after_lock" and audit["errors"] == []
        assert store.lock("synthetic")["forecast_id"] == version
    finally:
        store.close()


def test_official_audit_survives_recent_version_pagination(tmp_path, monkeypatch):
    from http_client import LocalClient

    from nfl_prediction.api.app import app

    store, clock, payload = fixture(tmp_path)
    try:
        official = store.publish(payload)
        kickoff = clock[0] + timedelta(hours=1)
        for index in range(25):
            clock[0] = kickoff - timedelta(minutes=4) + timedelta(seconds=index)
            store.publish(payload)
        clock[0] = kickoff + timedelta(hours=1)
        assert store.lock("synthetic")["forecast_id"] == official
        store.result(
            "synthetic",
            {"home_score": 21, "away_score": 20},
            status="settled",
            source_revision="final",
        )
        monkeypatch.setenv("NFL_DATA_DIR", str(tmp_path))
        with LocalClient(app) as client:
            audit = client.get("/api/games/synthetic").json()
            assert audit["official_forecast_id"] == official
            assert audit["errors"][0]["forecast_id"] == official
            assert any(v["id"] == official for v in audit["versions"])
            assert client.get("/api/games/synthetic/versions?limit=20").json()["total"] == 26
    finally:
        store.close()
