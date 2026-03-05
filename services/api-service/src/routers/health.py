from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from src.response import api_response

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    return api_response(
        {
            "status": "healthy",
            "service": "api-service",
            "timestamp": int(datetime.now(tz=timezone.utc).timestamp() * 1000),
        }
    )
