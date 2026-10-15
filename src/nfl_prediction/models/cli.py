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
