from __future__ import annotations

from fastapi import HTTPException, Request, WebSocket

from .config import settings

PUBLIC_PATHS = {
    "/signal/health",
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
        raise HTTPException(status_code=401, detail="unauthorized")


async def enforce_ws_auth(websocket: WebSocket) -> bool:
    if not settings.auth_enabled:
        return True
    token = websocket.headers.get("X-API-Token") or websocket.query_params.get("token")
    if token != settings.api_token:
        await websocket.accept()
        await websocket.send_json({"event": "error", "code": "40101", "msg": "unauthorized"})
        await websocket.close(code=1008)
        return False
    return True
