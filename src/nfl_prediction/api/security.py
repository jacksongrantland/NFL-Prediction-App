"""Local-only JSON write boundary for the single-user loopback application."""

from urllib.parse import urlsplit

from fastapi import Request
from starlette.responses import JSONResponse

from nfl_prediction.settings import Settings


async def local_writes(request: Request, call_next):
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return await call_next(request)
    loopbacks = {"127.0.0.1", "::1", "localhost"}
    host = request.url.hostname
    client = request.client.host if request.client else None
    origin = request.headers.get("origin")
    allowed_origin = True
    if origin:
        try:
            parsed = urlsplit(origin)
            allowed_origin = (
                parsed.scheme == "http"
                and parsed.hostname in loopbacks
                and parsed.port in {5173, 4173, Settings().port}
            )
        except ValueError:
            allowed_origin = False
    if (
        host not in loopbacks
        or client not in loopbacks
        or not allowed_origin
        or request.headers.get("x-nfl-local") != "1"
    ):
        return JSONResponse(
            {"detail": "Writes require loopback, trusted origin and X-NFL-Local: 1"},
            status_code=403,
        )
    if request.headers.get("content-type", "").split(";")[0] != "application/json":
        return JSONResponse({"detail": "JSON content type required"}, status_code=415)
    if len(await request.body()) > 65536:
        return JSONResponse({"detail": "Request body exceeds 64 KiB"}, status_code=413)
    return await call_next(request)
