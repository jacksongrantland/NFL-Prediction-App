"""Explicit local forecast publication, locking and audited result import."""

import json
from pathlib import Path

import typer

from nfl_prediction.storage.forecasts import ForecastStore

app = typer.Typer(help="Immutable local forecast history; no external publication.")


@app.command("publish")
def publish(
    payload: Path,
    retrospective: bool = typer.Option(False),
    data_dir: Path = typer.Option(Path("data")),
):
    """Store a fully described forecast; generation time cannot be supplied."""
    store = ForecastStore(data_dir)
    try:
        typer.echo(
            store.publish(
                json.loads(payload.read_text(encoding="utf-8-sig")), retrospective=retrospective
            )
        )
    finally:
        store.close()


@app.command("lock")
def lock(
    game_id: str,
    minutes_before: int = typer.Option(5, min=0),
    data_dir: Path = typer.Option(Path("data")),
):
    store = ForecastStore(data_dir)
    try:
        typer.echo(json.dumps(store.lock(game_id, minutes_before=minutes_before), indent=2))
    finally:
        store.close()


@app.command("result")
def result(
    game_id: str,
    actual: Path,
    source_revision: str,
    status: str = typer.Option("provisional"),
    data_dir: Path = typer.Option(Path("data")),
):
    store = ForecastStore(data_dir)
    try:
        typer.echo(
            store.result(
                game_id,
                json.loads(actual.read_text(encoding="utf-8-sig")),
                status=status,
                source_revision=source_revision,
            )
        )
    finally:
        store.close()


@app.command("audit")
def audit(game_id: str, data_dir: Path = typer.Option(Path("data"))):
    store = ForecastStore(data_dir)
    try:
        typer.echo(json.dumps(store.audit(game_id), indent=2))
    finally:
        store.close()


@app.command("reconcile")
def reconcile_results(season: int, data_dir: Path = typer.Option(Path("data"))):
    """Append completed-game actual revisions from the validated active snapshot."""
    from nfl_prediction.storage.forecasts import reconcile

    typer.echo(json.dumps(reconcile(data_dir, season), indent=2))
