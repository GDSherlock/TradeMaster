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


def _valid_symbol(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().upper()
    if re.fullmatch(r"[A-Z0-9]{2,20}", normalized):
        return normalized if normalized.endswith("USDT") else f"{normalized}USDT"
    return None


def _valid_interval(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    return normalized if normalized in VALID_INTERVALS else None


def _unwrap(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        if payload.get("success") is False:
            return None
        return payload.get("data")
    return payload


async def _fetch_active_signal(
    *,
    client: httpx.AsyncClient,
    base: str,
    symbol: str,
    interval: str,
    active_rule: str | None,
) -> dict[str, Any] | None:
    params: dict[str, Any] = {"symbol": symbol, "interval": interval, "include_ml": True, "limit": 1}
    if active_rule:
        params["rule_key"] = active_rule
    resp = await client.get(f"{base}/api/signal/events/latest", params=params)
    if resp.is_success:
        data = _unwrap(resp.json())
        if isinstance(data, list) and data:
            return data[0]
    if active_rule:
        fallback = await client.get(
            f"{base}/api/signal/events/latest",
            params={"symbol": symbol, "interval": interval, "include_ml": True, "limit": 1},
        )
        if fallback.is_success:
            data = _unwrap(fallback.json())
            if isinstance(data, list) and data:
                return data[0]
    return None


async def build_context(message: str, ui_context: dict[str, Any] | None = None) -> dict[str, Any]:
    symbol = _valid_symbol((ui_context or {}).get("symbol")) or _extract_symbol(message)
    interval = _valid_interval((ui_context or {}).get("interval")) or _extract_interval(message)
    active_rule = (ui_context or {}).get("active_rule")

    headers = {}
    if settings.api_service_token:
        headers["X-API-Token"] = settings.api_service_token

    base = settings.api_service_base_url.rstrip("/")

    async with httpx.AsyncClient(timeout=2.0, headers=headers) as client:
        reqs = [
            client.get(f"{base}/api/futures/ohlc/history", params={"symbol": symbol, "interval": interval, "limit": 30}),
            client.get(f"{base}/api/indicator/list"),
            client.get(f"{base}/api/markets/momentum"),
            _fetch_active_signal(client=client, base=base, symbol=symbol, interval=interval, active_rule=active_rule),
        ]
        candle_resp, indicator_list_resp, momentum_resp, signal_resp = await asyncio.gather(*reqs, return_exceptions=True)

    candles = None
    indicators = None
    momentum = None
    active_signal = None

    if isinstance(candle_resp, httpx.Response) and candle_resp.is_success:
        candles = _unwrap(candle_resp.json())
    if isinstance(indicator_list_resp, httpx.Response) and indicator_list_resp.is_success:
        indicators = _unwrap(indicator_list_resp.json())
    if isinstance(momentum_resp, httpx.Response) and momentum_resp.is_success:
        momentum = _unwrap(momentum_resp.json())
    if isinstance(signal_resp, dict):
        active_signal = signal_resp

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
        "active_signal": active_signal,
        "ui_context": ui_context or {},
    }
