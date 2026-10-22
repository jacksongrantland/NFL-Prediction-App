import asyncio

import httpx
import pytest
from pydantic import ValidationError

from nfl_prediction.api.app import app
from nfl_prediction.settings import Settings


def test_health_contract() -> None:
    async def request_health() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            return await client.get("/api/health")

    response = asyncio.run(request_health())
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "nfl-prediction", "version": "0.1.0"}


def test_public_network_binding_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(host="0.0.0.0", _env_file=None)
