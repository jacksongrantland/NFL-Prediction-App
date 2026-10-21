"""Synthetic causal extended baselines and raw lineage integrity checks."""

import copy

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from test_features import config
from test_features import history as history
from test_ingestion import fake_downloader
from test_ingestion import fixtures as fixtures

from nfl_prediction.data.ingest import SOURCES, run_ingestion
from nfl_prediction.features.pipeline import build_frames
from nfl_prediction.models.extended import FIELDS, forecast, load_actuals


def test_future_extended_actuals_cannot_change_earlier_forecasts(history):
    games, _ = build_frames(history, config())
    actual = history["team_stats"].copy()
    for stat, value in zip(FIELDS, [2, 1, 3, 2, 3, 1], strict=True):
        actual[stat] = float(value)
    original = forecast(actual, games, config(), "opponent")
    changed = copy.deepcopy(actual)
    changed.loc[changed.season.eq(2025), list(FIELDS)] = 99
    updated = forecast(changed, games, config(), "opponent")
    assert_frame_equal(original.loc[original.season.lt(2025)], updated.loc[updated.season.lt(2025)])
    assert (original.fg_made <= original.fg_att).all()
    assert (original.pat_made <= original.pat_att).all()
    assert original[list(FIELDS)].ge(0).all().all()


def test_expanded_raw_rows_are_exactly_reconciled_and_hash_checked(tmp_path, fixtures):
    raw_path = fixtures[SOURCES["team_stats"].format(season=2025)]
    raw = pd.read_parquet(raw_path)
    for stat, value in zip(FIELDS, [2, 1, 3, 2, 0, 0], strict=True):
        raw[stat] = value
    raw.to_parquet(raw_path, index=False)
    root = tmp_path / "data"
    run_ingestion([2025], root, current_season=2026, downloader_factory=fake_downloader(fixtures))
    _, actual, _, audit = load_actuals(root)
    assert len(actual) == 4 and audit[0]["nulls"]["fg_att"] == 0
    assert actual.fg_made.eq(1).all()
    from nfl_prediction.api.reads import query

    source = query(
        root, "SELECT raw_path FROM source_manifests WHERE manifest_json LIKE '%team_stats%'"
    )[0]
    from pathlib import Path

    Path(source["raw_path"]).write_bytes(b"corrupt-synthetic-source")
    with pytest.raises(ValueError, match="integrity"):
        load_actuals(root)
