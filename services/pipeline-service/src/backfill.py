from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from huggingface_hub import hf_hub_download

from .config import PROJECT_ROOT, settings
from .state_store import state_store
from .storage import storage

LOG = logging.getLogger(__name__)


def _retry(fn, attempts: int, base_sleep: float, message: str):
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            sleep_for = base_sleep * (2 ** i)
            LOG.warning("%s failed (%s/%s): %s", message, i + 1, attempts, exc)
            time.sleep(sleep_for)
    assert last_exc is not None
    raise last_exc


def _download_hf_file() -> Path:
    cache_dir = PROJECT_ROOT / "data" / "hf"
    cache_dir.mkdir(parents=True, exist_ok=True)

    def _dl() -> Path:
        p = hf_hub_download(
            repo_id=settings.hf_dataset,
            filename=settings.hf_candles_file,
            repo_type="dataset",
            local_dir=str(cache_dir),
            resume_download=True,
        )
        return Path(p)

    return _retry(_dl, attempts=5, base_sleep=1, message="hf download")


def _normalize_symbol(raw: str) -> str:
    s = raw.strip().upper()
    return s if s.endswith("USDT") else f"{s}USDT"


def run_backfill(symbols: list[str], days: int | None, resume: bool, chunk_rows: int) -> None:
    symbols = [_normalize_symbol(s) for s in symbols]
    symbols_set = set(symbols)
    cutoff = None
    if days and days > 0:
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)

    file_path = _download_hf_file()
    LOG.info("backfill source file: %s", file_path)

    last_ts_by_symbol: dict[str, datetime | None] = {s: None for s in symbols}
    if resume:
        for s in symbols:
            last_ts_by_symbol[s] = state_store.get_backfill_last_ts("hf_backfill", s, "1m")

    total_rows = 0
    for chunk in pd.read_csv(file_path, compression="gzip", chunksize=chunk_rows):
        if "symbol" not in chunk.columns or "bucket_ts" not in chunk.columns:
            raise ValueError("HF file missing required columns: symbol,bucket_ts")

        chunk = chunk[chunk["symbol"].astype(str).str.upper().isin(symbols_set)]
        if chunk.empty:
            continue

        chunk["symbol"] = chunk["symbol"].astype(str).str.upper()
        chunk["bucket_ts"] = pd.to_datetime(chunk["bucket_ts"], utc=True, errors="coerce")
        chunk = chunk.dropna(subset=["bucket_ts"])

        if cutoff is not None:
            chunk = chunk[chunk["bucket_ts"] >= cutoff]
        if chunk.empty:
            continue

        rows = []
        for _, r in chunk.iterrows():
            sym = str(r["symbol"]).upper()
            last_ts = last_ts_by_symbol.get(sym)
            ts = r["bucket_ts"].to_pydatetime()
            if resume and last_ts and ts <= last_ts:
                continue

            rows.append(
                {
                    "exchange": r.get("exchange", settings.default_exchange),
                    "symbol": sym,
                    "bucket_ts": ts,
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "volume": float(r.get("volume", 0)),
                    "quote_volume": float(r.get("quote_volume", 0)) if pd.notna(r.get("quote_volume", None)) else None,
                    "trade_count": int(r.get("trade_count", 0)) if pd.notna(r.get("trade_count", None)) else None,
                    "is_closed": True,
                    "source": "hf_backfill",
                }
            )
            if last_ts is None or ts > last_ts:
                last_ts_by_symbol[sym] = ts

        if not rows:
            continue

        def _write() -> int:
            return storage.upsert_candles(rows)

        written = _retry(_write, attempts=3, base_sleep=1, message="db upsert")
        total_rows += written

        for sym in symbols:
            state_store.set_backfill_state(
                source="hf_backfill",
                symbol=sym,
                interval="1m",
                last_ts=last_ts_by_symbol.get(sym),
                status="running",
                error_message=None,
            )

        LOG.info("backfill progress: +%s rows (total=%s)", written, total_rows)

    for sym in symbols:
        state_store.set_backfill_state(
            source="hf_backfill",
            symbol=sym,
            interval="1m",
            last_ts=last_ts_by_symbol.get(sym),
            status="done",
            error_message=None,
        )

    state_store.heartbeat("backfill", status="running", message=f"rows={total_rows}")
    LOG.info("backfill done rows=%s symbols=%s", total_rows, len(symbols))
