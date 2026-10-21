"""Explicit model operations; request handlers never train or download."""

import json
from pathlib import Path

import typer

app = typer.Typer(help="Train, evaluate and preview trusted local CPU models.")


@app.command("train-games")
def train_games(features: Path, output: Path = typer.Option(Path("artifacts/models"))) -> None:
    from nfl_prediction.models.games import train

    typer.echo(json.dumps(train(features, output), indent=2))


@app.command("evaluate-games")
def evaluate_games(model: Path) -> None:
    from nfl_prediction.models.games import evaluate

    typer.echo(json.dumps(evaluate(model), indent=2))


@app.command("preview-games")
def preview_games(model: Path, features: Path) -> None:
    from nfl_prediction.models.games import scheduled

    typer.echo(json.dumps(scheduled(model, features), indent=2))


@app.command("promote-games")
def promote_games(model: Path) -> None:
    from nfl_prediction.models.games import promote

    typer.echo(json.dumps(promote(model), indent=2))


@app.command("offense-baselines")
def offense_baselines(
    features: Path,
    participation: Path,
    data_dir: Path = typer.Option(Path("data")),
    output: Path = typer.Option(Path("artifacts/players")),
) -> None:
    """Evaluate explicit participation/opportunity baselines; missing stays unknown."""
    from nfl_prediction.models.players import run

    report = run(features, participation, data_dir, output)
    from nfl_prediction.models.player_io import load_manifest

    load_manifest(Path(report["path"]))
    typer.echo(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key not in ("validation", "final_test")
            },
            indent=2,
        )
    )


@app.command("preview-players")
def preview_players(model: Path, game_id: str) -> None:
    """Inspect an unpromoted baseline; missing roster games remain unsupported."""
    from nfl_prediction.models.player_io import preview

    typer.echo(json.dumps(preview(model, game_id), indent=2))


@app.command("select-offense")
def select_offense(
    features: Path,
    participation: Path,
    data_dir: Path = typer.Option(Path("data")),
    output: Path = typer.Option(Path("artifacts/player-defaults")),
) -> None:
    """Select defaults with nested earlier folds; never rescore the observed holdout."""
    from nfl_prediction.models.player_defaults import run

    report = run(features, participation, data_dir, output)
    typer.echo(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("validation", "selection_scores")},
            indent=2,
        )
    )
