"""Manual local roster entry and numerical fantasy comparison."""

import json
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from nfl_prediction import fantasy
from nfl_prediction.api import reads
from nfl_prediction.settings import Settings
from nfl_prediction.storage.forecasts import timestamp

router = APIRouter(prefix="/api/fantasy")


def candidates(root, season, week):
    result = []
    now = datetime.now(UTC)
    active = reads.snapshot(root, season)
    identities = reads.names(active["path"], active["id"]) if active else {}
    for game in reads.games(root, season):
        if game["week"] != week or not game["kickoff_at"] or timestamp(game["kickoff_at"]) <= now:
            continue
        versions = [
            v for v in reads.versions(root, game["game_id"]) if v["kind"] == "published_pregame"
        ]
        if not versions:
            continue
        version = versions[0]
        for player in version["summary"].get("player_summaries", []):
            identity = identities.get(player["player_id"])
            if not identity or identity["position"] not in ("QB", "RB", "WR", "TE"):
                continue
            result.append(
                {
                    "player_id": player["player_id"],
                    "team_id": player["team_id"],
                    "position": identity["position"],
                    "name": identity["name"],
                    "game_id": game["game_id"],
                    "forecast_id": version["id"],
                    "kickoff_at": game["kickoff_at"],
                    "availability_unknown": True,
                    "role_unknown": True,
                }
            )
    return result


@router.get("/players")
def available(
    season: int = Query(2026, ge=1999, le=2100),
    week: int = Query(7, ge=1, le=25),
    search: str = Query("", max_length=80),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
):
    rows = candidates(Settings().data_dir, season, week)
    rows = [
        r
        for r in rows
        if search.casefold() in f"{r['name']} {r['team_id']} {r['position']}".casefold()
    ]
    rows.sort(key=lambda r: (r["name"], r["player_id"]))
    return {
        "items": rows[offset : offset + limit],
        "total": len(rows),
        "offset": offset,
        "limit": limit,
    }


@router.get("/rosters/{identity}")
def roster(identity: str):
    try:
        path = fantasy.roster_path(Settings().data_dir, identity)
        if not path.exists():
            raise HTTPException(404, "No saved roster")
        return json.loads(path.read_text())
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/rosters/{identity}")
def save_roster(identity: str, body: fantasy.Roster):
    try:
        return fantasy.save(Settings().data_dir, identity, body)
    except (ValueError, OSError) as error:
        raise HTTPException(422, str(error)) from error


class ComparisonRequest(BaseModel):
    identity: str
    roster: fantasy.Roster
    scoring: fantasy.Scoring = fantasy.Scoring()
    risk: Literal["expected", "floor", "upside"] = "expected"


class Comparison(BaseModel):
    scoring: dict[str, Any]
    risk: str
    objective: str
    recommended: dict[str, Any]
    current: dict[str, Any] | None
    comparison: list[dict[str, Any]]
    expected_improvement: float | None
    forecast_versions: dict[str, str]
    locked_slots: dict[str, str]
    unknown_availability: bool
    recommended_for_decisions: bool
    limitations: str


@router.post("/compare", response_model=Comparison)
def compare(body: ComparisonRequest):
    try:
        saved_path = fantasy.roster_path(Settings().data_dir, body.identity)
        if not saved_path.exists():
            raise ValueError("Save the manual roster before comparing")
        previous = fantasy.Roster.model_validate(json.loads(saved_path.read_text())["roster"])
        now = datetime.now(UTC)
        kickoffs = {
            p.player_id: fantasy.entry_forecast(Settings().data_dir, p, now)["kickoff_at"]
            for p in previous.players
        }
        fantasy.validate_locked_change(previous, body.roster, kickoffs, now)
        return fantasy.recommend(
            Settings().data_dir, Settings().artifacts_dir, body.roster, body.scoring, risk=body.risk
        )
    except (ValueError, OSError) as error:
        raise HTTPException(422, str(error)) from error
