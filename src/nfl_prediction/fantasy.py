"""Versioned offensive fantasy scoring and exact slot assignment from joint samples."""

import json
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from nfl_prediction.api import reads
from nfl_prediction.data.ingest import ingestion_lock, json_hash
from nfl_prediction.models.simulation_io import read
from nfl_prediction.refresh import atomic_json
from nfl_prediction.storage.forecasts import timestamp

DEFAULT_SLOTS = {
    "QB": ["QB"],
    "RB1": ["RB"],
    "RB2": ["RB"],
    "WR1": ["WR"],
    "WR2": ["WR"],
    "TE": ["TE"],
    "FLEX": ["RB", "WR", "TE"],
}


class Scoring(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["offensive-fantasy/1"] = "offensive-fantasy/1"
    name: Literal["standard", "half_ppr", "ppr"] = "ppr"
    passing_yards: float = 0.04
    passing_tds: float = 4
    passing_interceptions: float = -2
    rushing_yards: float = 0.1
    rushing_tds: float = 6
    receiving_yards: float = 0.1
    receiving_tds: float = 6
    receptions: float | None = None

    def coefficients(self):
        result = self.model_dump(exclude={"version", "name", "receptions"})
        result["receptions"] = (
            self.receptions
            if self.receptions is not None
            else {"standard": 0, "half_ppr": 0.5, "ppr": 1}[self.name]
        )
        if not all(np.isfinite(value) for value in result.values()):
            raise ValueError("Scoring coefficients must be finite")
        return result


class Entry(BaseModel):
    player_id: str = Field(min_length=1, max_length=40)
    team_id: str = Field(min_length=2, max_length=3)
    game_id: str = Field(min_length=1, max_length=80)
    forecast_id: str = Field(min_length=1, max_length=64)
    position: Literal["QB", "RB", "WR", "TE"]
    name: str = Field(min_length=1, max_length=120)


class Roster(BaseModel):
    players: list[Entry] = Field(default_factory=list, max_length=40)
    slots: dict[str, list[str]] = Field(default_factory=lambda: dict(DEFAULT_SLOTS))
    lineup: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid(self):
        if not 1 <= len(self.slots) <= 12:
            raise ValueError("Use one to twelve lineup slots")
        if any(
            not allowed or not set(allowed) <= {"QB", "RB", "WR", "TE"}
            for allowed in self.slots.values()
        ):
            raise ValueError("Unsupported slot eligibility")
        if len({tuple(p.game_id.split("_")[:2]) for p in self.players}) > 1:
            raise ValueError("A roster comparison must use one season/week")
        ids = [p.player_id for p in self.players]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate player in roster")
        if not set(self.lineup) <= self.slots.keys() or not set(self.lineup.values()) <= set(ids):
            raise ValueError("Unknown lineup slot/player")
        if len(self.lineup.values()) != len(set(self.lineup.values())):
            raise ValueError("Player cannot occupy multiple slots")
        positions = {p.player_id: p.position for p in self.players}
        if any(positions[player] not in self.slots[slot] for slot, player in self.lineup.items()):
            raise ValueError("Ineligible player position for slot")
        return self


def score(samples: pd.DataFrame, rules: Scoring) -> np.ndarray:
    coefficients = rules.coefficients()
    if not set(coefficients) <= set(samples.columns):
        raise ValueError("Required supported scoring fields are missing")
    result = sum(
        samples[stat].to_numpy(dtype=float) * coefficient
        for stat, coefficient in coefficients.items()
    )
    if not np.isfinite(result).all():
        raise ValueError("Missing/nonfinite fantasy sample")
    return result


def optimize(
    roster: Roster,
    distributions: dict[str, np.ndarray],
    *,
    locked: dict[str, str],
    unavailable: set[str],
    risk: str = "expected",
) -> dict:
    penalty = {"expected": 0.0, "floor": -0.25, "upside": 0.25}
    if risk not in penalty:
        raise ValueError("Unknown risk preference")
    slots = list(roster.slots)
    slot_index = {s: i for i, s in enumerate(slots)}
    initial = sum(1 << slot_index[s] for s in locked)
    states = {initial: (0.0, dict(locked))}
    for player in roster.players:
        if player.player_id in unavailable or player.player_id in locked.values():
            continue
        values = distributions.get(player.player_id)
        if values is None:
            continue
        utility = float(values.mean() + penalty[risk] * values.std())
        updated = dict(states)
        for mask, (total, lineup) in states.items():
            for slot, allowed in roster.slots.items():
                bit = 1 << slot_index[slot]
                if mask & bit or player.position not in allowed:
                    continue
                new_mask, candidate = mask | bit, total + utility
                if new_mask not in updated or candidate > updated[new_mask][0]:
                    updated[new_mask] = (candidate, {**lineup, slot: player.player_id})
        states = updated
    full = (1 << len(slots)) - 1
    if full not in states:
        raise ValueError("Not enough supported eligible players to fill all slots")
    return states[full][1]


def validate_locked_change(previous: Roster, updated: Roster, kickoffs: dict, now: datetime):
    if previous.slots != updated.slots and any(timestamp(k) <= now for k in kickoffs.values()):
        raise ValueError("Cannot change slot definitions after a roster game starts")
    for slot, player in previous.lineup.items():
        if timestamp(kickoffs[player]) <= now and updated.lineup.get(slot) != player:
            raise ValueError("Started player's lineup slot is locked")
    started = {player for player, kickoff in kickoffs.items() if timestamp(kickoff) <= now}
    for slot, player in updated.lineup.items():
        if player in started and previous.lineup.get(slot) != player:
            raise ValueError("Started bench player cannot enter a lineup")
    previous_entries = {p.player_id: p for p in previous.players}
    for player in updated.players:
        if player.player_id in started:
            old = previous_entries[player.player_id]
            if (player.game_id, player.team_id, player.position) != (
                old.game_id,
                old.team_id,
                old.position,
            ):
                raise ValueError("Started player game/team/position is locked")
    if not started <= {p.player_id for p in updated.players}:
        raise ValueError("Started roster player cannot be removed")


def roster_path(root: Path, identity: str):
    if not identity or len(identity) > 64 or any(not (c.isalnum() or c in "-_") for c in identity):
        raise ValueError("Use a short alphanumeric roster name")
    return root / "fantasy" / "rosters" / f"{identity}.json"


def entry_forecast(root: Path, entry: Entry, now: datetime):
    version = reads.forecast(root, entry.forecast_id)
    if not version or version["game_id"] != entry.game_id or version["kind"] != "published_pregame":
        raise ValueError("Player requires an eligible published pregame forecast")
    kickoff = timestamp(version["kickoff_at"])
    if timestamp(version["generated_at"]) >= kickoff or timestamp(version["cutoff"]) >= kickoff:
        raise ValueError("Late forecast is ineligible")
    locked = reads.query(
        root, "SELECT forecast_id FROM forecast_locks WHERE game_id=?", (entry.game_id,)
    )
    if locked:
        if not locked[0]["forecast_id"]:
            raise ValueError("Game has no official eligible forecast; lineup stays locked")
        version = reads.forecast(root, locked[0]["forecast_id"])
        schedule = reads.query(
            root,
            "SELECT kickoff_at FROM forecast_schedule WHERE game_id=? ORDER BY id DESC LIMIT 1",
            (entry.game_id,),
        )
        if schedule and timestamp(schedule[0]["kickoff_at"]) != timestamp(version["kickoff_at"]):
            raise ValueError(
                "Locked game was rescheduled; no eligible comparison for the new kickoff"
            )
    elif now >= kickoff:
        raise ValueError("Started game has no official eligible forecast; lineup stays locked")
    else:
        current_game = next(
            (
                g
                for g in reads.games(root, int(entry.game_id.split("_")[0]))
                if g["game_id"] == entry.game_id
            ),
            None,
        )
        if current_game and timestamp(current_game["kickoff_at"]) != kickoff:
            raise ValueError("Game was rescheduled; a new eligible forecast is required")
    player = next(
        (
            p
            for p in version["summary"].get("player_summaries", [])
            if p["player_id"] == entry.player_id and p["team_id"] == entry.team_id
        ),
        None,
    )
    if player is None or entry.player_id == "other":
        raise ValueError("Unknown or aggregate player is ineligible")
    active = reads.snapshot(root, int(entry.game_id.split("_")[0]))
    identity = reads.names(active["path"], active["id"]).get(entry.player_id) if active else None
    if not identity or identity["position"] != entry.position:
        raise ValueError("Roster position must match the verified source identity")
    return version


def save(root: Path, identity: str, roster: Roster, *, now=None):
    with ingestion_lock(root, "fantasy.lock"):
        return _save(root, identity, roster, now=now)


def _save(root: Path, identity: str, roster: Roster, *, now=None):
    now = timestamp(now or datetime.now(UTC))
    path = roster_path(root, identity)
    versions = {p.player_id: entry_forecast(root, p, now) for p in roster.players}
    if path.exists():
        previous = Roster.model_validate(json.loads(path.read_text())["roster"])
        kickoffs = {
            p.player_id: entry_forecast(root, p, now)["kickoff_at"] for p in previous.players
        }
        validate_locked_change(previous, roster, kickoffs, now)
        previous_ids = {p.player_id for p in previous.players}
        if any(
            p.player_id not in previous_ids
            and now >= timestamp(versions[p.player_id]["kickoff_at"])
            for p in roster.players
        ):
            raise ValueError("Cannot add a player after kickoff")
    elif any(now >= timestamp(v["kickoff_at"]) for v in versions.values()):
        raise ValueError("Cannot initialize a roster containing started players")
    record = {"id": identity, "saved_at": now.isoformat(), "roster": roster.model_dump()}
    atomic_json(root / "fantasy" / "history" / f"{identity}-{json_hash(record)}.json", record)
    atomic_json(path, record)
    return record


@lru_cache(maxsize=2)
def samples(folder: str, simulation_id: str) -> pd.DataFrame:
    manifest = read(Path(folder))
    if manifest["simulation_id"] != simulation_id:
        raise ValueError("Simulation identity mismatch")
    return pd.read_parquet(Path(folder) / "player_draws.parquet")


def recommend(
    root: Path, artifacts: Path, roster: Roster, rules: Scoring, *, risk="expected", now=None
):
    now = timestamp(now or datetime.now(UTC))
    distributions, versions, unavailable, locked = {}, {}, set(), {}
    game_versions = {}
    for entry in roster.players:
        version = entry_forecast(root, entry, now)
        if entry.game_id in game_versions and game_versions[entry.game_id] != version["id"]:
            raise ValueError("Players from one game must use the same joint forecast version")
        game_versions[entry.game_id] = version["id"]
        folder = Path(version["simulation_config"]["artifact_path"]).resolve()
        if not folder.is_relative_to(artifacts.resolve()):
            raise ValueError(
                "Sample artifact must be inside the configured local artifact directory"
            )
        frame = samples(str(folder), version["simulation_config"]["simulation_id"])
        frame = frame.loc[
            frame.game_id.eq(entry.game_id)
            & frame.team_id.eq(entry.team_id)
            & frame.player_id.eq(entry.player_id)
        ].sort_values("draw")
        if frame.empty or not np.array_equal(frame.draw.to_numpy(), np.arange(len(frame))):
            raise ValueError("Missing/duplicate joint player samples")
        distributions[entry.player_id] = score(frame, rules)
        versions[entry.player_id] = version["id"]
        if now >= timestamp(version["kickoff_at"]):
            assigned = next((s for s, p in roster.lineup.items() if p == entry.player_id), None)
            if assigned:
                locked[assigned] = entry.player_id
            else:
                unavailable.add(entry.player_id)
    lineup = optimize(roster, distributions, locked=locked, unavailable=unavailable, risk=risk)
    count = min(len(v) for v in distributions.values())

    def describe(assignment):
        values = sum(distributions[p][:count] for p in assignment.values())
        return {
            "lineup": assignment,
            "expected": float(values.mean()),
            "p10": float(np.quantile(values, 0.1)),
            "p90": float(np.quantile(values, 0.9)),
            "standard_deviation": float(values.std()),
            "draws": count,
        }

    best = describe(lineup)
    alternative = describe(roster.lineup) if set(roster.lineup) == set(roster.slots) else None
    changes = [
        {
            "slot": slot,
            "recommended_player": player,
            "previous_player": roster.lineup.get(slot),
            "expected_points": float(distributions[player].mean()),
            "previous_expected_points": float(distributions[roster.lineup[slot]].mean())
            if slot in roster.lineup
            else None,
            "locked": slot in locked,
        }
        for slot, player in lineup.items()
    ]
    return {
        "scoring": rules.model_dump(),
        "risk": risk,
        "objective": {
            "expected": "Maximize expected supported offensive points",
            "floor": "Maximize sum of player mean minus 0.25 SD",
            "upside": "Maximize sum of player mean plus 0.25 SD",
        }[risk],
        "recommended": best,
        "current": alternative,
        "comparison": changes,
        "expected_improvement": best["expected"] - alternative["expected"] if alternative else None,
        "forecast_versions": versions,
        "locked_slots": locked,
        "unknown_availability": True,
        "recommended_for_decisions": False,
        "limitations": (
            "Experimental offensive subtotal; fumbles, two-point bonuses, kicking "
            "and defense excluded. Unknown depth roles/availability can alter rankings."
        ),
    }
