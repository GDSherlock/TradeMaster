from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx

from .config import settings

VALID_INTERVALS = {"1m", "5m", "15m", "1h", "4h", "1d"}


def _extract_symbol(message: str) -> str:
    m = re.search(r"\b([A-Z]{2,10}USDT)\b", message.upper())
    if m:
        return m.group(1)
    m = re.search(r"\b(BTC|ETH|SOL|BNB|XRP|DOGE)\b", message.upper())
    if m:
        return f"{m.group(1)}USDT"
    return "BTCUSDT"


def _extract_interval(message: str) -> str:
    m = re.search(r"\b(1m|5m|15m|1h|4h|1d)\b", message.lower())
    if m and m.group(1) in VALID_INTERVALS:
        return m.group(1)
    return "1h"


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        if payload.get("success") is False:
            return None
        return payload.get("data")
    return payload


async def build_context(message: str) -> dict[str, Any]:
    symbol = _extract_symbol(message)
    interval = _extract_interval(message)

    headers = {}
    if settings.api_service_token:
        headers["X-API-Token"] = settings.api_service_token

    base = settings.api_service_base_url.rstrip("/")

    async with httpx.AsyncClient(timeout=2.0, headers=headers) as client:
        reqs = [
            client.get(f"{base}/api/futures/ohlc/history", params={"symbol": symbol, "interval": interval, "limit": 30}),
            client.get(f"{base}/api/indicator/list"),
            client.get(f"{base}/api/markets/momentum"),
        ]
        candle_resp, indicator_list_resp, momentum_resp = await asyncio.gather(*reqs, return_exceptions=True)

    candles = None
    indicators = None
    momentum = None

    if isinstance(candle_resp, httpx.Response) and candle_resp.is_success:
        candles = _unwrap(candle_resp.json())
    if isinstance(indicator_list_resp, httpx.Response) and indicator_list_resp.is_success:
        indicators = _unwrap(indicator_list_resp.json())
    if isinstance(momentum_resp, httpx.Response) and momentum_resp.is_success:
        momentum = _unwrap(momentum_resp.json())

    indicator_row = None
    indicator_name = None
    if isinstance(indicators, list) and indicators:
        indicator_name = indicators[0]
        async with httpx.AsyncClient(timeout=2.0, headers=headers) as client:
            resp = await client.get(
                f"{base}/api/indicator/data",
                params={"table": indicator_name, "symbol": symbol, "interval": interval, "limit": 1},
            )
        if resp.is_success:
            data = _unwrap(resp.json())
            if isinstance(data, list) and data:
                indicator_row = data[0]

    return {
        "symbol": symbol,
        "interval": interval,
        "latest_candle": candles[-1] if isinstance(candles, list) and candles else None,
        "indicator_table": indicator_name,
        "indicator_row": indicator_row,
        "momentum": momentum,
    }
