"""Paper-only integer conservation, odds, pushes, cutoffs and correction history."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from nfl_prediction.paper import (
    Line,
    PaperStore,
    account,
    american_odds,
    decimal_odds,
    outcomes,
    payout,
)
from nfl_prediction.storage.forecasts import ForecastStore


def fixture(tmp_path):
    now = [datetime(2026, 10, 25, 16, tzinfo=UTC)]
    forecasts = ForecastStore(tmp_path, clock=lambda: now[0])
    payload = {
        "game_id": "2026_07_DAL_PHI",
        "cutoff": now[0].isoformat(),
        "kickoff_at": (now[0] + timedelta(hours=1)).isoformat(),
        "source_snapshots": {"synthetic": "test"},
        "input_freshness": {"status": "synthetic"},
        "model_versions": {"game": "synthetic"},
        "simulation_seed": 1,
        "simulation_config": {"count": 100},
        "supported_outputs": ["scores"],
        "summary": {"home_expected": 20, "away_expected": 10},
    }
    version = forecasts.publish(payload)
    store = PaperStore(tmp_path, clock=lambda: now[0])
    store.initialize("synthetic", 10000)
    line = store.line(Line(forecast_id=version, market="moneyline", selection="home", odds="+150"))
    return now, forecasts, store, version, line


def test_odds_conversion_pushes_and_exact_minor_unit_rounding():
    assert decimal_odds("+150", "american") == Decimal("2.5")
    assert decimal_odds("-200", "american") == Decimal("1.5")
    assert american_odds(Decimal("2.5")) == "150"
    assert american_odds(Decimal("1.5")) == "-200"
    assert payout(101, "win", Decimal("1.91")) == 192
    assert payout(101, "push", Decimal("1.91")) == 101
    assert outcomes([20], [20], {"market": "moneyline", "selection": "home"}).tolist() == [0]
    assert outcomes(
        [20], [17], {"market": "spread", "selection": "home", "points": "-3"}
    ).tolist() == [0]
    assert outcomes(
        [20], [17], {"market": "total", "selection": "under", "points": "37.5"}
    ).tolist() == [1]
    with pytest.raises(ValueError):
        decimal_odds("NaN", "decimal")
    with pytest.raises(ValueError):
        decimal_odds("-99", "american")


def test_atomic_stake_settlement_and_compensating_correction(tmp_path):
    now, forecasts, store, version, line = fixture(tmp_path)
    try:
        entry = store.enter("synthetic", version, line["id"], 1000, "one")
        assert account(tmp_path, "synthetic")["balance_minor"] == 9000
        with pytest.raises(ValueError, match="Duplicate"):
            store.enter("synthetic", version, line["id"], 1000, "one")
        with pytest.raises(ValueError, match="Insufficient"):
            store.enter("synthetic", version, line["id"], 10000, "two")
        now[0] += timedelta(hours=3)
        forecasts.result(
            "2026_07_DAL_PHI",
            {"home_score": 24, "away_score": 20},
            status="settled",
            source_revision="one",
        )
        assert store.settle(entry["id"])["return_minor"] == 2500
        assert account(tmp_path, "synthetic")["balance_minor"] == 11500
        with pytest.raises(ValueError, match="Duplicate"):
            store.settle(entry["id"])
        forecasts.result(
            "2026_07_DAL_PHI",
            {"home_score": 20, "away_score": 24},
            status="settled",
            source_revision="two",
        )
        correction = store.settle(entry["id"])
        assert correction["adjustment_minor"] == -2500
        result = account(tmp_path, "synthetic")
        assert result["balance_minor"] == 9000
        assert sum(row["amount_minor"] for row in result["ledger"]) == result["balance_minor"]
        assert result["settled_count"] == 1 and result["roi"] == -1
        with pytest.raises(IntegrityError, match="immutable"):
            store.db.execute("DELETE FROM paper_ledger")
    finally:
        store.close()
        forecasts.close()


def test_late_entries_and_provisional_settlement_rejected(tmp_path):
    now, forecasts, store, version, line = fixture(tmp_path)
    try:
        entry = store.enter("synthetic", version, line["id"], 1000, "one")
        now[0] += timedelta(minutes=55)
        with pytest.raises(ValueError, match="cutoff"):
            store.enter("synthetic", version, line["id"], 1000, "late")
        forecasts.result(
            "2026_07_DAL_PHI",
            {"home_score": 7, "away_score": 0},
            status="provisional",
            source_revision="provisional",
        )
        with pytest.raises(ValueError, match="Provisional"):
            store.settle(entry["id"])
        forecasts.result("2026_07_DAL_PHI", {}, status="cancelled", source_revision="cancelled")
        assert store.settle(entry["id"])["return_minor"] == 1000
    finally:
        store.close()
        forecasts.close()


def test_reschedule_voids_entry_and_preserves_evidence(tmp_path):
    now, forecasts, store, version, line = fixture(tmp_path)
    try:
        entry = store.enter("synthetic", version, line["id"], 1000, "one")
        now[0] += timedelta(minutes=1)
        forecasts.schedule("2026_07_DAL_PHI", now[0] + timedelta(days=1))
        result = store.settle(entry["id"])
        assert result["outcome"] == "void_rescheduled" and result["evidence_id"].startswith(
            "schedule:"
        )
        assert account(tmp_path, "synthetic")["balance_minor"] == 10000
        with pytest.raises(ValueError, match="Rescheduled"):
            store.enter("synthetic", version, line["id"], 1000, "two")
    finally:
        store.close()
        forecasts.close()


def test_correction_debt_is_explicit_and_blocks_new_virtual_spending(tmp_path):
    import json

    now, forecasts, store, version, line = fixture(tmp_path)
    try:
        first = store.enter("synthetic", version, line["id"], 10000, "first")
        now[0] += timedelta(hours=3)
        forecasts.result(
            "2026_07_DAL_PHI",
            {"home_score": 24, "away_score": 20},
            status="settled",
            source_revision="win",
        )
        store.settle(first["id"])
        previous = json.loads(
            store.db.one(
                "SELECT payload_json FROM forecast_versions WHERE id=:id", {"id": version}
            )["payload_json"]
        )
        for key in ("generated_at", "kind"):
            previous.pop(key)
        previous.update(
            game_id="2026_08_DAL_PHI",
            cutoff=now[0].isoformat(),
            kickoff_at=(now[0] + timedelta(days=7)).isoformat(),
        )
        future = forecasts.publish(previous)
        future_line = store.line(
            Line(forecast_id=future, market="moneyline", selection="home", odds="+100")
        )
        store.enter("synthetic", future, future_line["id"], 25000, "spent")
        forecasts.result(
            "2026_07_DAL_PHI",
            {"home_score": 20, "away_score": 24},
            status="settled",
            source_revision="corrected-loss",
        )
        assert store.settle(first["id"])["adjustment_minor"] == -25000
        assert account(tmp_path, "synthetic")["balance_minor"] == -25000
        with pytest.raises(ValueError, match="Insufficient"):
            store.enter("synthetic", future, future_line["id"], 1, "blocked")
    finally:
        store.close()
        forecasts.close()
