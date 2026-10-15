"""Small generated fixtures; these are not real NFL records or model data."""

import json
from pathlib import Path

import pandas as pd
import pytest

from nfl_prediction.data.downloads import Download, file_hash
from nfl_prediction.data.ingest import SOURCES, run_ingestion
from nfl_prediction.data.normalize import SOURCE_COLUMNS, normalize, reconcile
from nfl_prediction.storage.analytics import season_counts
from nfl_prediction.storage.database import Database


@pytest.fixture
def fixtures(tmp_path: Path) -> dict[str, Path]:
    raw = tmp_path / "synthetic_test_sources"
    raw.mkdir()
    games = [
        {
            "game_id": "2025_01_DAL_PHI",
            "season": 2025,
            "week": 1,
            "game_type": "REG",
            "gameday": "2025-09-04",
            "gametime": "20:20",
            "home_team": "PHI",
            "away_team": "DAL",
            "home_score": 24,
            "away_score": 20,
        },
        {
            "game_id": "2025_02_NYG_WAS",
            "season": 2025,
            "week": 2,
            "game_type": "REG",
            "gameday": "2025-09-14",
            "gametime": "13:00",
            "home_team": "WAS",
            "away_team": "NYG",
            "home_score": 17,
            "away_score": 21,
        },
    ]
    paths = {}
    for dataset, columns in SOURCE_COLUMNS.items():
        rows = []
        if dataset == "games":
            rows = games
        for game in games if dataset != "games" else []:
            week = game["week"]
            if dataset == "plays":
                row = dict.fromkeys(columns, 0)
                row.update(
                    {
                        "game_id": game["game_id"],
                        "play_id": 1,
                        "season": 2025,
                        "week": week,
                        "season_type": "REG",
                        "posteam": None,
                        "defteam": None,
                        "home_team": game["home_team"],
                        "away_team": game["away_team"],
                        "play_type_nfl": "END_GAME",
                        "game_seconds_remaining": 217 if week == 2 else 0,
                        "total_home_score": game["home_score"],
                        "total_away_score": game["away_score"],
                        "passer_player_id": None,
                        "rusher_player_id": None,
                        "receiver_player_id": None,
                    }
                )
                rows.append(row)
            else:
                for index, team in enumerate((game["away_team"], game["home_team"])):
                    row = dict.fromkeys(columns, 0)
                    row.update({"season": 2025, "week": week, "team": team})
                    player_id = "00-0000001" if index == 0 else f"00-000000{week + 1}"
                    if dataset in ("rosters", "weekly_rosters"):
                        row.update(
                            {
                                "game_type": "REG",
                                "gsis_id": player_id,
                                "pfr_id": "Test000",
                                "position": "QB",
                                "status": "ACT",
                                "full_name": "Synthetic fixture",
                            }
                        )
                    else:
                        row.update(
                            {
                                "game_id": game["game_id"],
                                "season_type": "REG",
                                "opponent_team": game["home_team"]
                                if index == 0
                                else game["away_team"],
                                "attempts": 2,
                                "completions": 1,
                                "passing_yards": -3,
                            }
                        )
                        if dataset == "player_stats":
                            row.update(player_id=player_id, position="QB")
                    rows.append(row)
        frame = pd.DataFrame(rows)
        path = raw / (dataset + (".csv" if dataset == "games" else ".parquet"))
        if dataset == "games":
            frame.to_csv(path, index=False)
        else:
            frame.to_parquet(path, index=False)
        paths[SOURCES[dataset].format(season=2025)] = path
    return paths


def fake_downloader(files: dict[str, Path]):
    class FixtureDownloader:
        downloaded_bytes = cache_hits = revalidated = 0

        def __init__(self, *_):
            pass

        def fetch(self, url, **_):
            if url not in files:
                raise OSError("Injected source failure")
            path = files[url]
            return Download(
                url, str(path), file_hash(path), path.stat().st_size, "2026-10-15T01:00:00Z"
            )

    return FixtureDownloader


def test_repeat_ingestion_preserves_snapshot_and_historical_team(fixtures, tmp_path):
    root = tmp_path / "data"
    factory = fake_downloader(fixtures)
    first = run_ingestion([2025], root, current_season=2026, downloader_factory=factory)
    second = run_ingestion([2025], root, current_season=2026, downloader_factory=factory)
    assert first["seasons"][0]["snapshot_id"] == second["seasons"][0]["snapshot_id"]
    assert second["seasons"][0]["reused"]
    assert season_counts(root, 2025)["team_stats"] == 4
    path = next((root / "normalized" / "2025").glob("*/player_stats.parquet"))
    players = pd.read_parquet(path)
    traded = players.loc[players.player_id.eq("00-0000001")].sort_values("week")
    assert traded.team_id.tolist() == ["DAL", "NYG"]
    assert traded.passing_yards.tolist() == [-3, -3]
    games = pd.read_parquet(path.with_name("games.parquet"))
    assert games.kickoff_at.iloc[0].isoformat() == "2025-09-05T00:20:00+00:00"
    assert games.result_status.eq("final").all()  # Includes walk-off OT with clock remaining.


def test_later_source_failure_cannot_publish_half_a_run(fixtures, tmp_path):
    root = tmp_path / "data"
    factory = fake_downloader(fixtures)
    run_ingestion([2025], root, current_season=2026, downloader_factory=factory)
    db = Database(root)
    before = db.one("SELECT snapshot_id FROM active_seasons WHERE season=2025")
    db.close()
    source = fixtures[SOURCES["player_stats"].format(season=2025)]
    revised = pd.read_parquet(source)
    revised.loc[0, "passing_yards"] = 100
    revised.to_parquet(source, index=False)
    with pytest.raises(OSError, match="Injected"):
        run_ingestion([2025, 2026], root, current_season=2026, downloader_factory=factory)
    db = Database(root)
    assert db.one("SELECT snapshot_id FROM active_seasons WHERE season=2025") == before
    assert db.one("SELECT snapshot_id FROM active_seasons WHERE season=2026") is None
    assert db.one("SELECT count(*) AS n FROM ingestion_runs WHERE status='failed'")["n"] == 1
    db.close()


def test_corrupt_normalized_snapshot_is_not_reused(fixtures, tmp_path):
    root = tmp_path / "data"
    factory = fake_downloader(fixtures)
    run_ingestion([2025], root, current_season=2026, downloader_factory=factory)
    file = next((root / "normalized").glob("*/*/plays.parquet"))
    file.write_bytes(b"corrupt generated test fixture")
    with pytest.raises(ValueError, match="integrity"):
        run_ingestion([2025], root, current_season=2026, downloader_factory=factory)


def test_conflicting_keys_and_unknown_alias_are_rejected(fixtures):
    frame = pd.read_parquet(fixtures[SOURCES["team_stats"].format(season=2025)])
    frame["source_row_number"] = range(1, len(frame) + 1)
    conflict = frame.iloc[[0]].copy()
    conflict["attempts"] = 3
    conflict["source_row_number"] = 100
    with pytest.raises(ValueError, match="conflicting duplicate"):
        normalize(pd.concat([frame, conflict]), "team_stats", 2025, "test-manifest")
    frame.loc[0, "team"] = "UNKNOWN"
    with pytest.raises(ValueError, match="Unknown team"):
        normalize(frame, "team_stats", 2025, "test-manifest")


def test_unresolved_roster_ids_are_reported_not_invented(fixtures):
    frame = pd.read_parquet(fixtures[SOURCES["rosters"].format(season=2025)])
    frame["source_row_number"] = range(1, len(frame) + 1)
    frame.loc[0, "gsis_id"] = ""
    normalized, summary, rejected = normalize(frame, "rosters", 2025, "test-manifest")
    assert summary["rejected_rows"] == 1
    assert len(normalized) == 3
    assert rejected.rejection_reason.tolist() == ["unresolved_gsis_id"]


def test_terminal_score_mismatch_prevents_finalization(fixtures):
    from nfl_prediction.data.normalize import read_source

    frames = {}
    for dataset, pattern in SOURCES.items():
        raw, _ = read_source(fixtures[pattern.format(season=2025)], dataset)
        frames[dataset], _, _ = normalize(raw, dataset, 2025, "test-manifest")
    frames["plays"].loc[0, "total_home_score"] = 99
    with pytest.raises(ValueError, match="score mismatch"):
        reconcile(frames)


def test_cached_manifest_has_no_invented_publication_time(fixtures, tmp_path):
    root = tmp_path / "data"
    run_ingestion([2025], root, current_season=2026, downloader_factory=fake_downloader(fixtures))
    manifests = [json.loads(path.read_text()) for path in (root / "raw/manifests").glob("*.json")]
    assert manifests
    assert all(m["checksum_scope"] == "full_artifact" for m in manifests)
    assert all(m["available_at"] is None and m["source_published_at"] is None for m in manifests)


def test_corrected_source_creates_new_snapshot_without_deleting_old(fixtures, tmp_path):
    root = tmp_path / "data"
    factory = fake_downloader(fixtures)
    first = run_ingestion([2025], root, current_season=2026, downloader_factory=factory)
    source = fixtures[SOURCES["player_stats"].format(season=2025)]
    revised = pd.read_parquet(source)
    revised.loc[0, "passing_yards"] = 100
    revised.to_parquet(source, index=False)
    second = run_ingestion(
        [2025], root, current_season=2026, downloader_factory=factory, force_refresh=True
    )
    assert first["seasons"][0]["snapshot_id"] != second["seasons"][0]["snapshot_id"]
    assert len(list((root / "normalized/2025").glob("*/summary.json"))) == 2


def test_os_lock_rejects_concurrent_ingestion(tmp_path):
    from nfl_prediction.data.ingest import ingestion_lock

    with ingestion_lock(tmp_path):
        with pytest.raises((RuntimeError, BlockingIOError)):
            with ingestion_lock(tmp_path):
                pytest.fail("Second lock unexpectedly succeeded")


def test_scores_without_terminal_pbp_do_not_finalize_or_enter_stats(fixtures):
    from nfl_prediction.data.normalize import read_source

    frames = {}
    for dataset, pattern in SOURCES.items():
        raw, _ = read_source(fixtures[pattern.format(season=2025)], dataset)
        frames[dataset], _, _ = normalize(raw, dataset, 2025, "test-manifest")
    frames["plays"].loc[frames["plays"].week.eq(2), "play_type_nfl"] = "PASS"
    coverage = reconcile(frames)
    assert coverage["completed_games"] == 1
    assert coverage["scored_but_unfinalized_games"] == ["2025_02_NYG_WAS"]
    assert frames["games"].result_status.tolist() == ["final", "provisional"]
    assert frames["player_stats"].week.eq(1).all()


def test_schedule_changes_are_versioned_per_season(fixtures, tmp_path):
    root = tmp_path / "data"
    factory = fake_downloader(fixtures)
    first = run_ingestion([2025], root, current_season=2026, downloader_factory=factory)
    source = fixtures[SOURCES["games"]]
    schedule = pd.read_csv(source)
    other_season = schedule.iloc[[0]].copy()
    other_season["season"] = 2026
    other_season["game_id"] = "2026_01_DAL_PHI"
    pd.concat([schedule, other_season]).to_csv(source, index=False)
    unchanged = run_ingestion([2025], root, current_season=2026, downloader_factory=factory)
    assert unchanged["seasons"][0]["snapshot_id"] == first["seasons"][0]["snapshot_id"]
    schedule.loc[0, "gametime"] = "21:20"
    schedule.to_csv(source, index=False)
    rescheduled = run_ingestion([2025], root, current_season=2026, downloader_factory=factory)
    assert rescheduled["seasons"][0]["snapshot_id"] != first["seasons"][0]["snapshot_id"]
