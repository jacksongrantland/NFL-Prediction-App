"""Paper-only endpoints; all writes use the shared loopback JSON boundary."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from nfl_prediction import paper
from nfl_prediction.api import reads
from nfl_prediction.settings import Settings

router = APIRouter(prefix="/api/paper")


class Seed(BaseModel):
    credits_minor: int = Field(default=100000, strict=True, ge=1, le=1_000_000_000)


class VirtualEntry(BaseModel):
    forecast_id: str = Field(min_length=1, max_length=64)
    line_id: str = Field(min_length=1, max_length=64)
    stake_minor: int = Field(strict=True, ge=1, le=1_000_000_000)
    idempotency_key: str = Field(min_length=1, max_length=100)


class PaperAccount(BaseModel):
    account_id: str
    initialized: bool
    balance_minor: int
    ledger: list[dict[str, Any]]
    entries: list[dict[str, Any]]
    settled_count: int
    roi: float | None
    net_settled_minor: int
    unit: str
    policy: str


def operation(action):
    store = paper.PaperStore(Settings().data_dir)
    try:
        return action(store)
    except (ValueError, OSError) as error:
        raise HTTPException(422, str(error)) from error
    finally:
        store.close()


@router.get("/accounts/{identity}", response_model=PaperAccount)
def account(identity: str):
    return paper.account(Settings().data_dir, identity)


@router.post("/accounts/{identity}")
def initialize(identity: str, body: Seed):
    return operation(lambda store: store.initialize(identity, body.credits_minor))


@router.post("/lines")
def line(body: paper.Line):
    def preview(store):
        saved = store.line(body)
        version = reads.forecast(Settings().data_dir, body.forecast_id)
        return {"line": saved, "estimate": paper.estimate(version, saved, Settings().artifacts_dir)}

    return operation(preview)


@router.post("/accounts/{identity}/entries")
def enter(identity: str, body: VirtualEntry):
    return operation(
        lambda store: store.enter(
            identity, body.forecast_id, body.line_id, body.stake_minor, body.idempotency_key
        )
    )


@router.post("/entries/{identity}/settle")
def settle(identity: str, body: dict):
    return operation(lambda store: store.settle(identity))
