"""Synchronous test facade over HTTPX ASGI transport; no deprecated TestClient."""

import asyncio

import httpx


class LocalClient:
    def __init__(self, app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)):
        self.app, self.base_url, self.client = app, base_url, client

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def request(self, method, path, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self.app, client=self.client)
            async with httpx.AsyncClient(transport=transport, base_url=self.base_url) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)
