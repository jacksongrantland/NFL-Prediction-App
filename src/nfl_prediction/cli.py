"""Windows-friendly CLI entry point."""

from datetime import UTC, datetime
from pathlib import Path

import typer
import uvicorn

from nfl_prediction import __version__
from nfl_prediction.models.cli import app as models_app
from nfl_prediction.settings import Settings

app = typer.Typer(help="Local NFL prediction tools.")
app.add_typer(models_app, name="models")


@app.command("build-features")
def build_features(
    data_dir: Path = typer.Option(Path("data")),
    output: Path = typer.Option(Path("artifacts/features")),
    smoke: bool = typer.Option(False),
) -> None:
    """Prepare weekly cutoff-aware features and train/validation/test manifests."""
    import json

    from nfl_prediction.features.pipeline import prepare

    try:
        seasons = None
        if smoke:
            from nfl_prediction.features.pipeline import load_history

            _, lineage = load_history(data_dir)
            seasons = sorted(map(int, lineage))[-4:]
        typer.echo(json.dumps(prepare(data_dir, output, seasons=seasons), indent=2))
    except (ValueError, OSError, RuntimeError) as error:
        typer.echo(f"Feature preparation failed: {error}", err=True)
        raise typer.Exit(1) from error


@app.command("check-backtest")
def check_backtest(path: Path) -> None:
    """Validate chronological folds and training-only preprocessing without scoring test data."""
    import json

    from nfl_prediction.evaluation.harness import check_folds

    typer.echo(json.dumps(check_folds(path), indent=2))


@app.command("capture-pregame")
def capture_pregame(
    season: int = typer.Option(..., min=1999, max=2100),
    data_dir: Path = typer.Option(Path("data")),
    injuries: bool = typer.Option(True, "--injuries/--no-injuries"),
) -> None:
    """Observe schedule, roster and optional structured injury sources now."""
    import json

    from nfl_prediction.data.snapshots import capture

    try:
        typer.echo(json.dumps(capture(season, data_dir, include_injuries=injuries), indent=2))
    except (ValueError, OSError, RuntimeError) as error:
        typer.echo(f"Capture failed: {error}", err=True)
        raise typer.Exit(1) from error


@app.command("import-availability")
def import_availability_csv(
    path: Path,
    season: int = typer.Option(..., min=1999, max=2100),
    data_dir: Path = typer.Option(Path("data")),
) -> None:
    """Validate and append a sourced manual availability CSV."""
    import json

    from nfl_prediction.data.snapshots import import_availability

    try:
        typer.echo(json.dumps(import_availability(path, season, data_dir), indent=2))
    except (ValueError, OSError, RuntimeError) as error:
        typer.echo(f"Import failed: {error}", err=True)
        raise typer.Exit(1) from error


@app.command("pregame-as-of")
def pregame_as_of(
    game_id: str,
    cutoff: str = typer.Option(..., help="Timezone-aware ISO 8601 timestamp."),
    season: int = typer.Option(..., min=1999, max=2100),
    data_dir: Path = typer.Option(Path("data")),
    stale_hours: float = typer.Option(36, min=0.001),
) -> None:
    """Read only observations recorded locally by a cutoff; unknown stays explicit."""
    import json

    from nfl_prediction.data.snapshots import as_of

    try:
        typer.echo(
            json.dumps(as_of(season, game_id, cutoff, data_dir, stale_hours=stale_hours), indent=2)
        )
    except (ValueError, OSError, RuntimeError) as error:
        typer.echo(f"Query failed: {error}", err=True)
        raise typer.Exit(1) from error


@app.command()
def ingest(
    season: list[int] | None = typer.Option(None, "--season", min=1999, max=2100),
    current_season: int | None = typer.Option(None, min=2006, max=2100),
    data_dir: Path = typer.Option(Path("data")),
    force_refresh: bool = typer.Option(False),
) -> None:
    """Ingest six completed seasons plus the current season; --season selects a smoke run."""
    import json

    from nfl_prediction.data.ingest import run_ingestion

    if current_season is None:
        now = datetime.now(UTC)
        current_season = now.year - (now.month < 3)
    seasons = season or list(range(current_season - 6, current_season + 1))
    if max(seasons) > current_season:
        raise typer.BadParameter("Cannot ingest a future NFL season.")
    try:
        report = run_ingestion(
            seasons, data_dir, current_season=current_season, force_refresh=force_refresh
        )
    except (ValueError, OSError, RuntimeError) as error:
        typer.echo(f"Ingestion failed; prior published snapshots retained: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(json.dumps(report, indent=2))


@app.command("data-counts")
def data_counts(season: int, data_dir: Path = typer.Option(Path("data"))) -> None:
    """Query the published season snapshot with an in-memory DuckDB connection."""
    import json

    from nfl_prediction.storage.analytics import season_counts

    try:
        typer.echo(json.dumps(season_counts(data_dir, season), indent=2))
    except (ValueError, OSError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(1) from error


@app.command("audit-sources")
def audit_sources(
    current_season: int | None = typer.Option(None, min=2006, max=2100),
    completed_seasons: int = typer.Option(6, min=1, max=20),
    output: Path = typer.Option(Path("data/audits/source_audit.json")),
) -> None:
    """Audit public source metadata and small samples; do not ingest full seasons."""
    from nfl_prediction.data.audit import run_audit, write_report

    if current_season is None:
        today = datetime.now(UTC)
        current_season = today.year - (today.month < 3)
    if current_season - completed_seasons < 1999:
        raise typer.BadParameter("The requested history must start in 1999 or later.")
    report = run_audit(current_season, completed_seasons)
    write_report(report, output)
    entries = [*report["datasets"], report["schedules"]]
    gaps = [entry for entry in entries if entry["status"] != "sample_verified"]
    typer.echo(f"Report: {output}; {len(entries) - len(gaps)}/{len(entries)} probes verified")
    for entry in gaps:
        typer.echo(f"  {entry['dataset']} {entry.get('season', '')}: {entry['status']}")
    if gaps:
        raise typer.Exit(code=1)


@app.command()
def version() -> None:
    """Print the application version."""
    typer.echo(__version__)


@app.command()
def serve() -> None:
    """Start the API on localhost using NFL_HOST and NFL_PORT settings."""
    settings = Settings()
    uvicorn.run("nfl_prediction.api.app:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    app()
