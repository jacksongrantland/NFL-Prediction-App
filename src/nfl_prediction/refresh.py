"""Repeatable local refresh, frozen-model inference and safe catch-up jobs."""

import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pandas as pd
from pydantic import BaseModel, Field

from nfl_prediction.data.downloads import Downloader
from nfl_prediction.data.ingest import ingestion_lock, run_ingestion
from nfl_prediction.data.snapshots import as_of, capture
from nfl_prediction.features.pipeline import load_history, prepare
from nfl_prediction.models.games import load
from nfl_prediction.models.player_defaults import infer
from nfl_prediction.models.player_io import load_manifest
from nfl_prediction.models.simulation_io import read
from nfl_prediction.models.simulation_io import run as simulate_week
from nfl_prediction.storage.forecasts import ForecastStore, reconcile, timestamp


class RefreshConfig(BaseModel):
    season: int = Field(ge=1999, le=2100)
    game_model: Path
    player_model: Path
    participation: Path
    data_dir: Path = Path("data")
    artifacts_dir: Path = Path("artifacts/refresh")
    count: int = Field(default=500, ge=100, le=5000)
    seed: int = 2026
    horizon_days: int = Field(default=8, ge=1, le=14)
    max_stale_hours: float = Field(default=36, gt=0)
    request_interval_seconds: float = Field(default=0.5, ge=0.5, le=60)
    minimum_refresh_minutes: int = Field(default=10, ge=1)
    daily_hour_chicago: int = Field(default=8, ge=0, le=23)
    pregame_minutes: list[int] = Field(default_factory=lambda: [90, 30, 10])
    lock_minutes: int = Field(default=5, ge=0)


def due(config: RefreshConfig, now: datetime, last_success, kickoffs: list) -> bool:
    if last_success is None:
        return True
    previous = timestamp(last_success)
    if now - previous < timedelta(minutes=config.minimum_refresh_minutes):
        return False
    local = now.astimezone(ZoneInfo("America/Chicago"))
    daily = local.replace(hour=config.daily_hour_chicago, minute=0, second=0, microsecond=0)
    if local >= daily and previous < daily:
        return True
    return any(
        previous < timestamp(kickoff) - timedelta(minutes=minutes) <= now < timestamp(kickoff)
        for kickoff in kickoffs
        for minutes in config.pregame_minutes
    )


def publication_eligible(now: datetime, kickoff, observations: dict, *, stale_hours: float) -> bool:
    if now >= timestamp(kickoff):
        return False
    return all(
        observations.get(f"{kind}_freshness") == "observed" for kind in ("schedule", "roster")
    )


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}-{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def execute_steps(steps: list, report: dict, checkpoint):
    """Persist each successful boundary; a failed dependency prevents later steps."""
    try:
        for name, action in steps:
            result = action()
            report["steps"].append({"step": name, "status": "succeeded", "result": result})
            checkpoint(report)
        report["status"] = "succeeded"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        checkpoint(report)
        raise
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        checkpoint(report)


def refresh(
    config: RefreshConfig, *, fetch_sources: bool = True, scheduled: bool = False, clock=None
) -> dict:
    clock = clock or (lambda: datetime.now(UTC))
    start = time.perf_counter()
    state_dir = config.data_dir / "refresh"
    last_path = state_dir / "last_success.json"
    with ingestion_lock(config.data_dir, "refresh.lock"):
        now = timestamp(clock())
        history, _ = load_history(config.data_dir, [config.season])
        previous = json.loads(last_path.read_text()) if last_path.exists() else None
        if scheduled and not due(
            config,
            now,
            previous["finished_at"] if previous else None,
            history["games"].kickoff_at.dropna().tolist(),
        ):
            # Locks/results still catch up even when downloads are not due.
            return maintenance(config, clock=clock) | {"status": "not_due"}
        _, game_model = load(config.game_model)
        player_model = load_manifest(config.player_model)
        if game_model["promotion_status"] != "promoted_local":
            raise ValueError("Explicitly promote an evaluated local game model before refresh")
        if player_model["promotion_status"] != "local_baseline_default":
            raise ValueError("Select a local player baseline before refresh")
        report = {
            "run_id": uuid4().hex,
            "started_at": now.isoformat(),
            "status": "running",
            "steps": [],
        }
        log_path = state_dir / "runs" / f"{report['run_id']}.json"
        state = {}

        def checkpoint(value):
            atomic_json(log_path, value)

        def source_step():
            def downloader(root, db):
                return Downloader(root, db, request_interval=config.request_interval_seconds)

            if not fetch_sources:
                return {
                    "mode": "cached_verified_sources",
                    "warning": "Freshness checks still apply",
                }
            ingested = run_ingestion(
                [config.season],
                config.data_dir,
                current_season=config.season,
                downloader_factory=downloader,
            )
            observed = capture(config.season, config.data_dir, downloader_factory=downloader)
            return {"ingestion": ingested, "observations": observed}

        def feature_step():
            state["features"] = prepare(
                config.data_dir, config.artifacts_dir / "features", live_cutoff=timestamp(clock())
            )
            return {
                "feature_id": state["features"]["feature_id"],
                "path": state["features"]["path"],
            }

        def inference_step():
            state["players"] = infer(
                Path(state["features"]["path"]),
                config.participation,
                config.data_dir,
                config.player_model,
                config.artifacts_dir / "players",
            )
            return {"player_inference_id": state["players"]["player_model_id"]}

        def prediction_step():
            path = Path(state["features"]["path"])
            games = pd.read_parquet(path / "games.parquet")
            current = timestamp(clock())
            upcoming = games.loc[
                games.kickoff_at.gt(current)
                & games.kickoff_at.le(current + timedelta(days=config.horizon_days))
            ]
            state["simulations"] = []
            for (season, week), week_games in upcoming.groupby(["season", "week"]):
                result = simulate_week(
                    config.game_model,
                    Path(state["players"]["path"]),
                    path,
                    config.artifacts_dir / "simulations",
                    season=int(season),
                    week=int(week),
                    count=config.count,
                    seed=config.seed,
                    game_ids=week_games.game_id.tolist(),
                )
                state["simulations"].append(result)
            return {"simulation_ids": [r["simulation_id"] for r in state["simulations"]]}

        def publication_step():
            store = ForecastStore(config.data_dir, clock=clock)
            published, skipped = [], []
            try:
                games = pd.read_parquet(
                    Path(state["features"]["path"]) / "games.parquet"
                ).set_index("game_id")
                for artifact in state["simulations"]:
                    folder = Path(artifact["path"])
                    read(folder)
                    summaries = json.loads((folder / "summaries.json").read_text())
                    for summary in summaries:
                        game = games.loc[summary["game_id"]]
                        current = timestamp(clock())
                        observed = as_of(
                            int(game.season),
                            summary["game_id"],
                            current,
                            config.data_dir,
                            stale_hours=config.max_stale_hours,
                        )
                        if not publication_eligible(
                            current, game.kickoff_at, observed, stale_hours=config.max_stale_hours
                        ):
                            skipped.append(
                                {
                                    "game_id": summary["game_id"],
                                    "reason": "late_or_stale_schedule_roster",
                                }
                            )
                            continue
                        if observed["game"]["kickoff_at"] != game.kickoff_at.isoformat().replace(
                            "+00:00", "Z"
                        ):
                            # Compare timestamps, not formatting conventions.
                            if timestamp(observed["game"]["kickoff_at"]) != timestamp(
                                game.kickoff_at
                            ):
                                raise ValueError("Kickoff changed after feature generation")
                        payload = {
                            "game_id": summary["game_id"],
                            "cutoff": game.cutoff.isoformat(),
                            "kickoff_at": game.kickoff_at.isoformat(),
                            "source_snapshots": state["features"]["source_snapshots"],
                            "input_freshness": {
                                k: observed[k]
                                for k in (
                                    "schedule_freshness",
                                    "roster_freshness",
                                    "injury_source_status",
                                    "schedule_batch_id",
                                    "roster_batch_id",
                                    "mode",
                                )
                            },
                            "model_versions": {
                                "game": game_model["model_id"],
                                "player": player_model["player_model_id"],
                                "player_inference": state["players"]["player_model_id"],
                            },
                            "simulation_seed": summary["seed"],
                            "simulation_config": {
                                "count": config.count,
                                "accounting_version": "simulation/1",
                                "artifact_path": str(folder.resolve()),
                                "simulation_id": artifact["simulation_id"],
                            },
                            "supported_outputs": ["scores", "QB_RB_WR_TE_offense"],
                            "summary": summary,
                        }
                        try:
                            published.append(store.publish(payload))
                        except ValueError as error:
                            if (
                                "locked" in str(error)
                                or "late" in str(error)
                                or "kickoff" in str(error).lower()
                            ):
                                skipped.append(
                                    {"game_id": summary["game_id"], "reason": str(error)}
                                )
                            else:
                                raise
                return {"forecast_ids": published, "skipped": skipped}
            finally:
                store.close()

        steps = [
            ("sources", source_step),
            ("features", feature_step),
            ("frozen_model_inference", inference_step),
            ("joint_prediction", prediction_step),
            ("publication", publication_step),
            ("lock_and_reconcile", lambda: maintenance(config, clock=clock)),
        ]
        execute_steps(steps, report, checkpoint)
        report["elapsed_seconds"] = round(time.perf_counter() - start, 3)
        checkpoint(report)
        atomic_json(last_path, report)
        return report


def maintenance(config: RefreshConfig, *, clock=None) -> dict:
    clock = clock or (lambda: datetime.now(UTC))
    history, _ = load_history(config.data_dir, [config.season])
    store = ForecastStore(config.data_dir, clock=clock)
    locks = []
    try:
        for game in history["games"].to_dict("records"):
            if pd.isna(game["kickoff_at"]):
                continue
            store.schedule(game["game_id"], game["kickoff_at"])
            if timestamp(clock()) >= timestamp(game["kickoff_at"]) - timedelta(
                minutes=config.lock_minutes
            ):
                locks.append(store.lock(game["game_id"], minutes_before=config.lock_minutes))
        return {
            "locks_checked": len(locks),
            "results": reconcile(config.data_dir, config.season, clock=clock),
        }
    finally:
        store.close()
