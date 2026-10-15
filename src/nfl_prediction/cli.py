"""Windows-friendly CLI entry point."""

import typer
import uvicorn

from nfl_prediction import __version__
from nfl_prediction.settings import Settings

app = typer.Typer(help="Local NFL prediction tools.")


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
