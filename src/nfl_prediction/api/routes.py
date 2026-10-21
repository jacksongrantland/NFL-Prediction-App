"""Typed paginated read endpoints over immutable local snapshots and history."""

import json
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from nfl_prediction.api import reads
from nfl_prediction.settings import Settings

router = APIRouter(prefix="/api")


class Game(BaseModel):
    game_id: str
    season: int
    week: int
    game_type: str
    home_team_id: str
    away_team_id: str
    kickoff_at: str | None
    home_score: int | None
    away_score: int | None
    result_status: str
    forecast_count: int
    official_forecast_id: str | None
    lock_status: str


class GamePage(BaseModel):
    items: list[Game]
    total: int
    offset: int
    limit: int


class Distribution(BaseModel):
    mean: float
    p10: float
    p90: float


class PlayerForecast(BaseModel):
    team_id: str
    player_id: str
    name: str
    position: str | None = None
    offense_participation_probability: float
    availability_unknown: bool = True
    role_unknown: bool = True
    stats: dict[str, Distribution]
    active_conditional: dict[str, Distribution | None]


class PlayerPage(BaseModel):
    items: list[PlayerForecast]
    total: int
    offset: int
    limit: int


class Forecast(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    game_id: str
    generated_at: str
    cutoff: str
    kickoff_at: str
    kind: Literal["published_pregame", "retrospective"]
    source_snapshots: dict[str, str]
    input_freshness: dict[str, Any]
    model_versions: dict[str, str]
    simulation_seed: int
    simulation_config: dict[str, Any]
    supported_outputs: list[str]
    summary: dict[str, Any]


class Audit(BaseModel):
    game_id: str
    versions: list[Forecast]
    official_forecast_id: str | None
    locks: list[dict[str, Any]]
    actuals: list[dict[str, Any]]
    errors: list[dict[str, Any]]


class Freshness(BaseModel):
    active_snapshots: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    last_refresh: dict[str, Any] | None
    limitations: str


class Evaluation(BaseModel):
    kind: str
    records: dict[str, Any]
    published_history: dict[str, Any]
    limitations: str


def root():
    return Settings().data_dir


@router.get("/games", response_model=GamePage)
def list_games(
    season: int = Query(2026, ge=1999, le=2100),
    week: int | None = Query(None, ge=1, le=25),
    team: str | None = Query(None, max_length=3),
    offset: int = Query(0, ge=0),
    limit: int = Query(32, ge=1, le=100),
):
    rows = reads.games(root(), season)
    if week is not None:
        rows = [r for r in rows if r["week"] == week]
    if team:
        rows = [r for r in rows if team.upper() in (r["home_team_id"], r["away_team_id"])]
    return {
        "items": rows[offset : offset + limit],
        "total": len(rows),
        "offset": offset,
        "limit": limit,
    }


@router.get("/games/{game_id}", response_model=Audit)
def game_detail(game_id: str):
    return reads.audit(root(), game_id)


@router.get("/forecasts/{forecast_id}", response_model=Forecast)
def version(forecast_id: str):
    result = reads.forecast(root(), forecast_id)
    if not result:
        raise HTTPException(404, "Forecast version not found")
    return result


@router.get("/forecasts/{forecast_id}/players", response_model=PlayerPage)
def players(
    forecast_id: str,
    team: str | None = Query(None, max_length=3),
    position: str | None = Query(None, max_length=2),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    result = reads.forecast(root(), forecast_id)
    if not result:
        raise HTTPException(404, "Forecast version not found")
    active = reads.snapshot(root(), int(result["game_id"].split("_")[0]))
    identities = reads.names(active["path"], active["id"]) if active else {}
    rows = [
        {
            **r,
            **identities.get(
                r["player_id"],
                {
                    "name": "Other players" if r["player_id"] == "other" else r["player_id"],
                    "position": None,
                },
            ),
        }
        for r in result["summary"].get("player_summaries", [])
    ]
    if team:
        rows = [r for r in rows if r["team_id"] == team.upper()]
    if position:
        rows = [r for r in rows if r["position"] == position.upper()]
    return {
        "items": rows[offset : offset + limit],
        "total": len(rows),
        "offset": offset,
        "limit": limit,
    }


@router.get("/freshness", response_model=Freshness)
def freshness():
    snapshots = reads.query(root(), "SELECT season,snapshot_id FROM active_seasons ORDER BY season")
    observations = reads.query(
        root(),
        "SELECT kind, MAX(observed_at) AS observed_at, MAX(recorded_at) AS recorded_at "
        "FROM observation_batches GROUP BY kind",
    )
    path = root() / "refresh" / "last_success.json"
    refresh = json.loads(path.read_text()) if path.exists() else None
    if refresh:
        refresh = {
            k: refresh[k]
            for k in ("run_id", "finished_at", "status", "elapsed_seconds")
            if k in refresh
        }
    return {
        "active_snapshots": snapshots,
        "observations": observations,
        "last_refresh": refresh,
        "limitations": (
            "Observation time is local knowledge, not historical source publication. "
            "Unknown availability is not healthy."
        ),
    }


@router.get("/evaluation", response_model=Evaluation)
def evaluation():
    docs = Path(__file__).parents[3] / "docs"
    records = {}
    for kind, name in (
        ("games", "game_model_verification_2026-10-15.json"),
        ("players", "offense_default_verification_2026-10-21.json"),
        ("simulation", "simulation_verification_2026-10-21.json"),
        ("team_components", "team_component_verification_2026-10-21.json"),
    ):
        path = docs / name
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8-sig"))
            records[kind] = value
    locked = reads.query(
        root(), "SELECT COUNT(*) AS n FROM forecast_locks WHERE forecast_id IS NOT NULL"
    )
    return {
        "kind": "approximate_historical_backtest",
        "records": records,
        "published_history": {"official_locked_forecasts": locked[0]["n"] if locked else 0},
        "limitations": (
            "Backtests and the small selected validation week are not published "
            "pregame performance or evidence of a betting advantage."
        ),
    }


class VersionPage(BaseModel):
    items: list[Forecast]
    total: int
    offset: int
    limit: int


@router.get("/games/{game_id}/versions", response_model=VersionPage)
def version_history(
    game_id: str, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)
):
    rows = reads.versions(root(), game_id, limit=limit, offset=offset)
    count = reads.query(
        root(), "SELECT COUNT(*) AS n FROM forecast_versions WHERE game_id=?", (game_id,)
    )
    return {"items": rows, "total": count[0]["n"] if count else 0, "offset": offset, "limit": limit}


class TeamForecast(BaseModel):
    team_id: str
    expected_score: float
    score_p10: float
    score_p90: float
    win_probability: float
    tie_probability: float
    components: dict[str, Distribution] = {}
    scope: str = "Joint-sample scoring; individual kicking/defense unsupported"


@router.get("/forecasts/{forecast_id}/teams", response_model=list[TeamForecast])
def team_forecasts(forecast_id: str):
    result = reads.forecast(root(), forecast_id)
    if not result:
        raise HTTPException(404, "Forecast version not found")
    season = int(result["game_id"].split("_")[0])
    game = next((g for g in reads.games(root(), season) if g["game_id"] == result["game_id"]), None)
    if not game:
        raise HTTPException(404, "Source game unavailable")
    summary = result["summary"]
    return [
        {
            "team_id": game[f"{side}_team_id"],
            "expected_score": summary[f"{side}_expected"],
            "score_p10": summary[f"{side}_p10_p90"][0],
            "score_p90": summary[f"{side}_p10_p90"][1],
            "win_probability": summary[f"{side}_win"],
            "tie_probability": summary["tie"],
            "components": summary.get("team_stat_summaries", {}).get(side, {}),
            "scope": "Evaluated team kicking/sacks/interceptions; individual roles unsupported"
            if summary.get("team_stat_summaries")
            else "Joint scoring; aggregate kicking/defense approximation",
        }
        for side in ("home", "away")
    ]
