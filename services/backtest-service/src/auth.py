from __future__ import annotations

from fastapi import HTTPException, Request

from .config import settings
from .response import ErrorCode

PUBLIC_PATHS = {
    "/backtest/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}


def enforce_http_auth(request: Request) -> None:
    if not settings.auth_enabled:
        return
    if request.url.path in PUBLIC_PATHS:
        return
    token = request.headers.get("X-API-Token", "")
    if token != settings.api_token:
        raise HTTPException(status_code=401, detail=ErrorCode.UNAUTHORIZED.value)
