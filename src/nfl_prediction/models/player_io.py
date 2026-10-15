"""Integrity-checked access to experimental local offensive baselines."""

import json
from pathlib import Path

import pandas as pd

from nfl_prediction.data.downloads import file_hash


def load_manifest(folder: Path) -> dict:
    manifest = json.loads((folder / "manifest.json").read_text())
    for name, checksum in manifest["files"].items():
        if file_hash(folder / name) != checksum:
            raise ValueError("Player artifact integrity failure")
    return manifest


def preview(folder: Path, game_id: str) -> dict:
    manifest = load_manifest(folder)
    rows = pd.read_parquet(folder / "projections.parquet")
    rows = rows.loc[rows.game_id.eq(game_id)]
    projections = json.loads(rows.to_json(orient="records", date_format="iso"))
    for row in projections:
        row["availability_scenarios"] = {
            "offensive_participation": {
                stat: row[f"conditional_{stat}"] for stat in manifest["config"]["stats"]
            },
            "no_offensive_participation": dict.fromkeys(manifest["config"]["stats"], 0),
            "policy": "Counterfactual scenarios, not injury-derived probabilities.",
        }
    return {
        "game_id": game_id,
        "player_model_id": manifest["player_model_id"],
        "forecast_type": "unpublished_experimental_baseline_preview",
        "promotion_status": manifest["promotion_status"],
        "recommended_for_decisions": False,
        "status": "available" if len(rows) else "unsupported_roster_or_game",
        "projections": projections,
    }
