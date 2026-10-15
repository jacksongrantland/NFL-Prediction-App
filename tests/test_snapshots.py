"""Synthetic source observations only; timestamps are controlled by a fake clock."""

import csv
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy.exc import IntegrityError
from test_ingestion import fake_downloader
from test_ingestion import fixtures as fixtures

from nfl_prediction.data import snapshots
from nfl_prediction.data.ingest import SOURCES
from nfl_prediction.data.snapshots import (
    INJURIES_URL,
    MANUAL_COLUMNS,
    as_of,
    capture,
    import_availability,
    injury_rows,
    timestamp,
)
from nfl_prediction.storage.database import Database


@pytest.fixture
def clock(monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 10, 15, 12, tzinfo=UTC)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz or UTC)

    monkeypatch.setattr(snapshots, "datetime", Clock)
    return Clock


def manual_csv(path, **changes):
    row = dict.fromkeys(MANUAL_COLUMNS, "")
    row.update(
        player_id="00-0000001",
        game_id="2025_01_DAL_PHI",
        team_id="DAL",
        source_url="https://example.com/report",
        published_at="2026-10-15T11:00:00Z",
        observed_at="2026-10-15T12:00:00Z",
        injury_designation="Questionable",
    )
    row.update(changes)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=MANUAL_COLUMNS)
        writer.writeheader()
        writer.writerow(row)
    return path


def test_capture_preserves_revisions_and_cutoff_excludes_future(fixtures, tmp_path, clock):
    root = tmp_path / "data"
    factory = fake_downloader(fixtures)
    capture(2025, root, include_injuries=False, downloader_factory=factory)
    early = clock.current
    path = fixtures[SOURCES["games"]]
    raw = pd.read_csv(path)
    raw.loc[0, "gametime"] = "21:20"
    raw.to_csv(path, index=False)
    clock.current += timedelta(hours=2)
    capture(2025, root, include_injuries=False, downloader_factory=factory)
    old = as_of(2025, "2025_01_DAL_PHI", early, root)
    new = as_of(2025, "2025_01_DAL_PHI", clock.current, root)
    assert old["game"]["source_gametime"] == "20:20"
    assert new["game"]["source_gametime"] == "21:20"
    assert old["injury_source_status"] == "disabled"
    assert old["mode"] == "no_injury_data"
    assert all(p["game_inactive"] is None for p in old["availability"])
    assert as_of(2025, "2025_01_DAL_PHI", early - timedelta(seconds=1), root)["game"] is None


def test_manual_report_changes_do_not_rewrite_earlier_cutoffs(fixtures, tmp_path, clock):
    root = tmp_path / "data"
    capture(2025, root, include_injuries=False, downloader_factory=fake_downloader(fixtures))
    clock.current += timedelta(hours=1)
    path = manual_csv(tmp_path / "input.csv")
    import_availability(path, 2025, root)
    early = clock.current
    # An earlier claimed publication/observation does not bypass local recording time.
    clock.current += timedelta(hours=1)
    manual_csv(path, injury_designation="Out", game_inactive="true")
    import_availability(path, 2025, root)
    before = as_of(2025, "2025_01_DAL_PHI", early, root)
    after = as_of(2025, "2025_01_DAL_PHI", clock.current, root)
    assert before["availability"][0]["injury_designation"] == "Questionable"
    assert before["availability"][0]["game_inactive"] is None
    assert after["availability"][0]["injury_designation"] == "Out"
    assert after["availability"][0]["game_inactive"] is True
    assert after["availability"][0]["practice_participation"] is None
    stale = as_of(2025, "2025_01_DAL_PHI", clock.current + timedelta(days=3), root)
    assert stale["availability"][0]["freshness"] == "stale"
    assert stale["mode"] == "no_injury_data"
    db = Database(root)
    with pytest.raises(IntegrityError, match="immutable"):
        db.execute("DELETE FROM observation_batches")
    db.close()


@pytest.mark.parametrize(
    "change",
    [
        {"game_inactive": "maybe"},
        {"observed_at": "2026-10-15T12:00:00"},
        {"observed_at": "2099-01-01T00:00:00Z"},
        {"team_id": "NYG"},
        {"player_id": "Someone"},
        {"source_url": "missing"},
        {"published_at": "2099-01-01T00:00:00Z"},
    ],
)
def test_invalid_manual_import_is_atomic(fixtures, tmp_path, clock, change):
    root = tmp_path / "data"
    capture(2025, root, include_injuries=False, downloader_factory=fake_downloader(fixtures))
    with pytest.raises(ValueError):
        import_availability(manual_csv(tmp_path / "bad.csv", **change), 2025, root)
    db = Database(root)
    assert db.one("SELECT count(*) AS n FROM observation_batches")["n"] == 3
    db.close()


def test_free_injury_adapter_preserves_fields_and_reports_unmapped(fixtures, tmp_path, clock):
    path = tmp_path / "synthetic_injuries.parquet"
    rows = [
        {
            "season": 2025,
            "week": 1,
            "game_type": "REG",
            "team": "DAL",
            "gsis_id": "00-0000001",
            "report_status": "Questionable",
            "practice_status": "Limited",
            "report_primary_injury": "Ankle",
        }
    ]
    rows.append({**rows[0], "gsis_id": None})
    pd.DataFrame(rows).to_parquet(path)
    fixtures[INJURIES_URL.format(season=2025)] = path
    report = capture(2025, tmp_path / "data", downloader_factory=fake_downloader(fixtures))
    assert report["datasets"][-1]["rejected_rows"] == 1
    result = as_of(2025, "2025_01_DAL_PHI", clock.current, tmp_path / "data")
    player = result["availability"][0]
    assert player["injury_designation"] == "Questionable"
    assert player["practice_participation"] == "Limited"
    assert player["published_at"] is None
    assert player["game_inactive"] is None
    games = pd.DataFrame([{**result["game"], "season": 2025, "week": 1}])
    with pytest.raises(ValueError, match="Ambiguous duplicate"):
        injury_rows(pd.DataFrame([rows[0], rows[0]]), games, 2025)


def test_optional_injury_failure_keeps_useful_schedule_and_roster(fixtures, tmp_path, clock):
    report = capture(2025, tmp_path / "data", downloader_factory=fake_downloader(fixtures))
    assert report["datasets"][-1]["status"] == "unavailable"
    result = as_of(2025, "2025_01_DAL_PHI", clock.current, tmp_path / "data")
    assert result["game"] and result["roster"]
    assert result["injury_source_status"] == "unavailable"
    assert result["mode"] == "no_injury_data"


def test_timezone_offsets_are_equivalent():
    assert timestamp("2026-10-15T07:00:00-05:00") == timestamp("2026-10-15T12:00:00Z")
    with pytest.raises(ValueError, match="timezone"):
        timestamp("2026-10-15T12:00:00")


def test_required_source_failure_does_not_publish_partial_capture(fixtures, tmp_path, clock):
    del fixtures[SOURCES["rosters"].format(season=2025)]
    root = tmp_path / "data"
    with pytest.raises(OSError, match="Injected"):
        capture(2025, root, downloader_factory=fake_downloader(fixtures))
    db = Database(root)
    assert db.one("SELECT count(*) AS n FROM observation_batches")["n"] == 0
    db.close()


def test_bad_second_manual_row_does_not_publish_first(fixtures, tmp_path, clock):
    root = tmp_path / "data"
    capture(2025, root, include_injuries=False, downloader_factory=fake_downloader(fixtures))
    path = manual_csv(tmp_path / "input.csv")
    content = path.read_text()
    path.write_text(content + content.splitlines()[1].replace("00-0000001", "bad-id") + "\n")
    with pytest.raises(ValueError, match="player_id"):
        import_availability(path, 2025, root)
    db = Database(root)
    assert db.one("SELECT count(*) AS n FROM observation_batches WHERE source='manual'")["n"] == 0
    db.close()
