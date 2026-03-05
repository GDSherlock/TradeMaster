from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import datetime, timedelta, timezone

import httpx
import websockets

from .config import settings
from .state_store import state_store
from .storage import storage

LOG = logging.getLogger(__name__)


def _stream_url(symbols: list[str]) -> str:
    streams = "/".join(f"{s.lower()}@kline_1m" for s in symbols)
    return f"{settings.ws_url}?streams={streams}"


def _row_from_ws(msg: dict) -> dict | None:
    data = msg.get("data") or {}
    k = data.get("k") or {}
    if not k.get("x"):
        return None

    ts = datetime.fromtimestamp(int(k["t"]) / 1000, tz=timezone.utc)
    return {
        "exchange": settings.default_exchange,
        "symbol": str(k.get("s", "")).upper(),
        "bucket_ts": ts,
        "open": float(k.get("o", 0)),
        "high": float(k.get("h", 0)),
        "low": float(k.get("l", 0)),
        "close": float(k.get("c", 0)),
        "volume": float(k.get("v", 0)),
        "quote_volume": float(k.get("q", 0)) if k.get("q") is not None else None,
        "trade_count": int(k.get("n", 0)) if k.get("n") is not None else None,
        "is_closed": True,
        "source": "ws_live",
    }


def _rest_gap_fill(symbols: list[str]) -> int:
    total = 0
    with httpx.Client(timeout=10) as client:
        for sym in symbols:
            r = client.get(
                "https://fapi.binance.com/fapi/v1/klines",
                params={"symbol": sym, "interval": "1m", "limit": 5},
            )
            r.raise_for_status()
            payload = r.json()
            rows = []
            for item in payload:
                ts = datetime.fromtimestamp(int(item[0]) / 1000, tz=timezone.utc)
                if ts < datetime.now(tz=timezone.utc) - timedelta(minutes=5):
                    continue
                rows.append(
                    {
                        "exchange": settings.default_exchange,
                        "symbol": sym,
                        "bucket_ts": ts,
                        "open": float(item[1]),
                        "high": float(item[2]),
                        "low": float(item[3]),
                        "close": float(item[4]),
                        "volume": float(item[5]),
                        "quote_volume": float(item[7]) if item[7] is not None else None,
                        "trade_count": int(item[8]) if item[8] is not None else None,
                        "is_closed": True,
                        "source": "rest_gap_fill",
                    }
                )
            total += storage.upsert_candles(rows)
    return total


async def run_live(symbols: list[str]) -> None:
    symbols = [s.upper() for s in symbols]
    url = _stream_url(symbols)
    backoff = 1
    max_backoff = max(1, settings.ws_reconnect_max_seconds)
    buffer: list[dict] = []
    last_flush = time.time()
    last_fallback = time.time()
    last_heartbeat = 0.0

    while True:
        try:
            LOG.info("connect ws %s", url)
            async with websockets.connect(url, ping_interval=20, ping_timeout=20, max_size=2_000_000) as ws:
                backoff = 1
                while True:
                    now = time.time()
                    if now - last_heartbeat >= 10:
                        state_store.heartbeat("live_ws", status="running", message=f"buffer={len(buffer)}")
                        last_heartbeat = now

                    if now - last_flush >= settings.ws_flush_seconds and buffer:
                        written = storage.upsert_candles(buffer)
                        buffer.clear()
                        last_flush = now
                        LOG.info("ws flush rows=%s", written)

                    if now - last_fallback >= settings.rest_fallback_interval_seconds:
                        try:
                            added = await asyncio.to_thread(_rest_gap_fill, symbols)
                            LOG.info("rest fallback rows=%s", added)
                        except Exception as exc:  # noqa: BLE001
                            LOG.warning("rest fallback failed: %s", exc)
                        last_fallback = now

                    message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    payload = json.loads(message)
                    row = _row_from_ws(payload)
                    if row:
                        buffer.append(row)
        except Exception as exc:  # noqa: BLE001
            state_store.heartbeat("live_ws", status="degraded", message=str(exc)[:200])
            wait = min(max_backoff, backoff) + random.uniform(0, 0.3)
            LOG.warning("ws disconnected: %s, reconnect in %.1fs", exc, wait)
            if buffer:
                try:
                    storage.upsert_candles(buffer)
                except Exception:  # noqa: BLE001
                    LOG.exception("flush on disconnect failed")
                finally:
                    buffer.clear()
            await asyncio.sleep(wait)
            backoff = min(max_backoff, backoff * 2)
