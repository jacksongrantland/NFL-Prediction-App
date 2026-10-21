"""Small read-only API; prediction endpoints arrive in later stages."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from nfl_prediction import __version__
from nfl_prediction.api.routes import router


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


app = FastAPI(title="NFL Prediction API", version=__version__)
app.include_router(router)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="nfl-prediction", version=__version__)
