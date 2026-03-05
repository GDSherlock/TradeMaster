from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    SUCCESS = "0"
    PARAM_ERROR = "40001"
    UNAUTHORIZED = "40101"
    RATE_LIMITED = "42901"
    SERVICE_UNAVAILABLE = "50001"
    INTERNAL_ERROR = "50002"


def api_response(data: Any, code: ErrorCode = ErrorCode.SUCCESS, msg: str = "success") -> dict:
    return {
        "code": code.value,
        "msg": msg,
        "data": data,
        "success": code == ErrorCode.SUCCESS,
    }


def error_response(code: ErrorCode, msg: str) -> dict:
    return {
        "code": code.value,
        "msg": msg,
        "data": None,
        "success": False,
    }
