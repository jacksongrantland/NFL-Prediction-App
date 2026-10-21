"""Small read-only API; prediction endpoints arrive in later stages."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from nfl_prediction import __version__
from nfl_prediction.api.fantasy_routes import router as fantasy_router
from nfl_prediction.api.paper_routes import router as paper_router
from nfl_prediction.api.routes import router
from nfl_prediction.api.security import local_writes


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


app = FastAPI(title="NFL Prediction API", version=__version__)
app.include_router(router)
app.include_router(fantasy_router)
app.include_router(paper_router)
app.middleware("http")(local_writes)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="nfl-prediction", version=__version__)
