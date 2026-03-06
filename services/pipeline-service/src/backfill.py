from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from huggingface_hub import HfApi, hf_hub_download

from .config import PROJECT_ROOT, settings
from .indicator_engine import run_historical_backfill
from .state_store import state_store
from .storage import storage

LOG = logging.getLogger(__name__)

ALLOWED_BACKFILL_SYMBOLS = {"BTCUSDT", "BNBUSDT", "ETHUSDT", "SOLUSDT"}
BACKFILL_SOURCE = "hf_backfill"
BACKFILL_INTERVAL = "1m"
BACKFILL_LOCK_NAME = "pipeline-service:hf-backfill:candles_1m"
MAX_ERROR_MESSAGE_LENGTH = 500
HF_REQUIRED_COLUMNS = {"symbol", "bucket_ts", "open", "high", "low", "close"}
HF_OPTIONAL_COLUMNS = {"exchange", "volume", "quote_volume", "trade_count"}


def _retry(fn, attempts: int, base_sleep: float, message: str):
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            sleep_for = base_sleep * (2**i)
            LOG.warning("%s failed (%s/%s): %s", message, i + 1, attempts, exc)
            time.sleep(sleep_for)
    assert last_exc is not None
    raise last_exc


def _normalize_symbol(raw: str) -> str:
    s = raw.strip().upper()
    return s if s.endswith("USDT") else f"{s}USDT"


def _normalize_symbols(symbols: list[str]) -> list[str]:
    normalized = [_normalize_symbol(symbol) for symbol in symbols]
    unsupported = sorted(set(normalized) - ALLOWED_BACKFILL_SYMBOLS)
    if unsupported:
        joined = ",".join(unsupported)
        raise ValueError(f"unsupported backfill symbols: {joined}")
    return normalized


def _floor_minute(ts: datetime) -> datetime:
    return ts.astimezone(timezone.utc).replace(second=0, microsecond=0)


def _truncate_error(exc: Exception) -> str:
    return str(exc).replace("\n", " ")[:MAX_ERROR_MESSAGE_LENGTH]


def _fetch_dataset_revision() -> str:
    info = HfApi().dataset_info(repo_id=settings.hf_dataset)
    revision = getattr(info, "sha", None)
    return str(revision or "unknown")


def _download_hf_file() -> tuple[Path, str]:
    cache_dir = PROJECT_ROOT / "data" / "hf"
    cache_dir.mkdir(parents=True, exist_ok=True)

    def _dl() -> Path:
        path = hf_hub_download(
            repo_id=settings.hf_dataset,
            filename=settings.hf_candles_file,
            repo_type="dataset",
            local_dir=str(cache_dir),
            resume_download=True,
        )
        return Path(path)

    file_path = _retry(_dl, attempts=5, base_sleep=1, message="hf download")

    try:
        dataset_revision = _retry(_fetch_dataset_revision, attempts=3, base_sleep=1, message="hf dataset info")
    except Exception as exc:  # noqa: BLE001
        LOG.warning("hf dataset revision unavailable: %s", exc)
        dataset_revision = "unknown"

    return file_path, dataset_revision


def _resolve_window(
    days: int | None,
    start_ts: datetime | None,
    end_ts: datetime | None,
    live_guard_minutes: int,
) -> tuple[datetime | None, datetime]:
    guard_minutes = max(1, live_guard_minutes)
    live_cutoff = _floor_minute(datetime.now(tz=timezone.utc) - timedelta(minutes=guard_minutes))
    resolved_end = min(end_ts, live_cutoff) if end_ts else live_cutoff
    resolved_start = start_ts
    if resolved_start is None and days and days > 0:
        resolved_start = resolved_end - timedelta(days=days)
    if resolved_start and resolved_start > resolved_end:
        raise ValueError("backfill start_ts must be earlier than end_ts")
    return resolved_start, resolved_end


def _usecols(column_name: str) -> bool:
    return column_name in HF_REQUIRED_COLUMNS or column_name in HF_OPTIONAL_COLUMNS


def _state_matches_request(
    row: dict[str, Any] | None,
    *,
    dataset_revision: str,
    chunk_rows: int,
    requested_start_ts: datetime | None,
    requested_end_ts: datetime,
    explicit_start: bool,
    explicit_end: bool,
) -> bool:
    if row is None:
        return False
    stored_revision = str(row.get("dataset_revision") or "")
    stored_chunk_rows = row.get("chunk_rows")
    stored_start = row.get("requested_start_ts")
    stored_end = row.get("requested_end_ts")

    if stored_revision != dataset_revision:
        return False
    if stored_chunk_rows is None or int(stored_chunk_rows) != chunk_rows:
        return False
    if explicit_start and stored_start != requested_start_ts:
        return False
    if explicit_end and stored_end != requested_end_ts:
        return False
    if not explicit_end and stored_end is not None and stored_end > requested_end_ts:
        return False
    return True


def _load_resume_state(
    symbols: list[str],
    *,
    resume: bool,
    dataset_revision: str,
    chunk_rows: int,
    requested_start_ts: datetime | None,
    requested_end_ts: datetime,
    explicit_start: bool,
    explicit_end: bool,
) -> tuple[int, dict[str, datetime | None], int]:
    last_ts_by_symbol: dict[str, datetime | None] = {symbol: None for symbol in symbols}
    if not resume:
        return 0, last_ts_by_symbol, 0

    state_rows = {
        symbol: state_store.get_backfill_state(BACKFILL_SOURCE, symbol, BACKFILL_INTERVAL)
        for symbol in symbols
    }
    existing_rows = [row for row in state_rows.values() if row]
    if not existing_rows:
        return 0, last_ts_by_symbol, 0

    compatible = all(
        _state_matches_request(
            row,
            dataset_revision=dataset_revision,
            chunk_rows=chunk_rows,
            requested_start_ts=requested_start_ts,
            requested_end_ts=requested_end_ts,
            explicit_start=explicit_start,
            explicit_end=explicit_end,
        )
        for row in existing_rows
    )
    if not compatible:
        LOG.info("resume checkpoint reset due to request/dataset mismatch")
        return 0, last_ts_by_symbol, 0

    scan_chunk_index = max(int(row.get("scan_chunk_index") or 0) for row in existing_rows)
    rows_written = max(int(row.get("rows_written") or 0) for row in existing_rows)
    for symbol, row in state_rows.items():
        if row:
            last_ts_by_symbol[symbol] = row.get("last_ts")

    LOG.info("resume checkpoint loaded chunk_index=%s rows_written=%s", scan_chunk_index, rows_written)
    return scan_chunk_index, last_ts_by_symbol, rows_written


def _write_backfill_state(
    symbols: list[str],
    *,
    last_ts_by_symbol: dict[str, datetime | None],
    status: str,
    error_message: str | None,
    scan_chunk_index: int | None,
    chunk_rows: int,
    requested_start_ts: datetime | None,
    requested_end_ts: datetime,
    rows_written: int,
    dataset_revision: str,
) -> None:
    for symbol in symbols:
        state_store.set_backfill_state(
            source=BACKFILL_SOURCE,
            symbol=symbol,
            interval=BACKFILL_INTERVAL,
            last_ts=last_ts_by_symbol.get(symbol),
            status=status,
            error_message=error_message,
            scan_chunk_index=scan_chunk_index,
            chunk_rows=chunk_rows,
            requested_start_ts=requested_start_ts,
            requested_end_ts=requested_end_ts,
            rows_written=rows_written,
            dataset_revision=dataset_revision,
        )


def _prepare_chunk(
    chunk: pd.DataFrame,
    *,
    symbols_set: set[str],
    requested_start_ts: datetime | None,
    requested_end_ts: datetime,
) -> pd.DataFrame:
    missing = HF_REQUIRED_COLUMNS - set(chunk.columns)
    if missing:
        required = ",".join(sorted(HF_REQUIRED_COLUMNS))
        actual = ",".join(sorted(chunk.columns))
        missing_cols = ",".join(sorted(missing))
        raise ValueError(
            f"HF file missing required columns: {required}; actual={actual}; missing={missing_cols}"
        )

    filtered = chunk[chunk["symbol"].astype(str).str.upper().isin(symbols_set)].copy()
    if filtered.empty:
        return filtered

    filtered["symbol"] = filtered["symbol"].astype(str).str.upper()
    filtered["bucket_ts"] = pd.to_datetime(filtered["bucket_ts"], utc=True, errors="coerce")
    filtered = filtered.dropna(subset=["bucket_ts"])
    if requested_start_ts is not None:
        filtered = filtered[filtered["bucket_ts"] >= requested_start_ts]
    filtered = filtered[filtered["bucket_ts"] <= requested_end_ts]
    if filtered.empty:
        return filtered

    if "exchange" in filtered.columns:
        filtered["exchange"] = filtered["exchange"].fillna(settings.default_exchange).astype(str)
    else:
        filtered["exchange"] = settings.default_exchange
    if "volume" in filtered.columns:
        filtered["volume"] = pd.to_numeric(filtered["volume"], errors="coerce").fillna(0.0)
    else:
        filtered["volume"] = 0.0
    if "quote_volume" in filtered.columns:
        filtered["quote_volume"] = pd.to_numeric(filtered["quote_volume"], errors="coerce")
    else:
        filtered["quote_volume"] = None
    if "trade_count" in filtered.columns:
        filtered["trade_count"] = pd.to_numeric(filtered["trade_count"], errors="coerce")
    else:
        filtered["trade_count"] = None
    filtered = filtered.sort_values(["symbol", "bucket_ts"], kind="mergesort")
    return filtered


def _commit_candle_batch(
    rows: list[dict[str, Any]],
    batch_last_ts: dict[str, datetime],
    *,
    symbols: list[str],
    last_ts_by_symbol: dict[str, datetime | None],
    total_rows: int,
    chunk_index: int,
    chunk_rows: int,
    requested_start_ts: datetime | None,
    requested_end_ts: datetime,
    dataset_revision: str,
) -> int:
    if not rows:
        return total_rows

    written = _retry(lambda: storage.upsert_candles(rows), attempts=3, base_sleep=1, message="db upsert")
    total_rows += written
    for symbol, ts in batch_last_ts.items():
        current = last_ts_by_symbol.get(symbol)
        if current is None or ts > current:
            last_ts_by_symbol[symbol] = ts

    _write_backfill_state(
        symbols,
        last_ts_by_symbol=last_ts_by_symbol,
        status="running",
        error_message=None,
        scan_chunk_index=chunk_index,
        chunk_rows=chunk_rows,
        requested_start_ts=requested_start_ts,
        requested_end_ts=requested_end_ts,
        rows_written=total_rows,
        dataset_revision=dataset_revision,
    )
    return total_rows


def run_backfill(
    symbols: list[str],
    days: int | None,
    resume: bool,
    chunk_rows: int,
    *,
    start_ts: datetime | None = None,
    end_ts: datetime | None = None,
    live_guard_minutes: int | None = None,
    with_indicators: bool | None = None,
    db_batch_rows: int | None = None,
    intervals: list[str] | None = None,
) -> None:
    normalized_symbols = _normalize_symbols(symbols)
    symbols_set = set(normalized_symbols)
    resolved_live_guard = live_guard_minutes if live_guard_minutes is not None else settings.backfill_live_guard_minutes
    requested_start_ts, requested_end_ts = _resolve_window(days, start_ts, end_ts, resolved_live_guard)
    resolved_with_indicators = settings.backfill_with_indicators if with_indicators is None else with_indicators
    resolved_db_batch_rows = max(1, db_batch_rows or settings.backfill_db_batch_rows)
    indicator_intervals = [interval.lower() for interval in (intervals or settings.intervals)]
    explicit_start = start_ts is not None
    explicit_end = end_ts is not None

    file_path, dataset_revision = _download_hf_file()
    LOG.info(
        "backfill source file=%s revision=%s start=%s end=%s symbols=%s",
        file_path,
        dataset_revision,
        requested_start_ts,
        requested_end_ts,
        ",".join(normalized_symbols),
    )

    scan_chunk_index, last_ts_by_symbol, total_rows = _load_resume_state(
        normalized_symbols,
        resume=resume,
        dataset_revision=dataset_revision,
        chunk_rows=chunk_rows,
        requested_start_ts=requested_start_ts,
        requested_end_ts=requested_end_ts,
        explicit_start=explicit_start,
        explicit_end=explicit_end,
    )

    observed_max_ts = max((ts for ts in last_ts_by_symbol.values() if ts is not None), default=None)
    current_scan_chunk_index = scan_chunk_index

    try:
        with storage.advisory_lock(BACKFILL_LOCK_NAME):
            for chunk_index, chunk in enumerate(
                pd.read_csv(file_path, compression="gzip", chunksize=chunk_rows, usecols=_usecols)
            ):
                if chunk_index < scan_chunk_index:
                    continue

                prepared = _prepare_chunk(
                    chunk,
                    symbols_set=symbols_set,
                    requested_start_ts=requested_start_ts,
                    requested_end_ts=requested_end_ts,
                )
                if prepared.empty:
                    continue
                current_scan_chunk_index = chunk_index

                batch_rows: list[dict[str, Any]] = []
                batch_last_ts: dict[str, datetime] = {}

                for record in prepared.to_dict(orient="records"):
                    symbol = str(record["symbol"]).upper()
                    ts_value = record["bucket_ts"]
                    ts = ts_value.to_pydatetime() if hasattr(ts_value, "to_pydatetime") else ts_value

                    last_ts = last_ts_by_symbol.get(symbol)
                    if resume and last_ts and ts <= last_ts:
                        continue

                    row = {
                        "exchange": str(record.get("exchange") or settings.default_exchange),
                        "symbol": symbol,
                        "bucket_ts": ts,
                        "open": float(record["open"]),
                        "high": float(record["high"]),
                        "low": float(record["low"]),
                        "close": float(record["close"]),
                        "volume": float(record.get("volume", 0) or 0),
                        "quote_volume": (
                            float(record["quote_volume"]) if pd.notna(record.get("quote_volume", None)) else None
                        ),
                        "trade_count": (
                            int(record["trade_count"]) if pd.notna(record.get("trade_count", None)) else None
                        ),
                        "is_closed": True,
                        "source": BACKFILL_SOURCE,
                    }
                    batch_rows.append(row)
                    batch_last_ts[symbol] = ts
                    observed_max_ts = ts if observed_max_ts is None or ts > observed_max_ts else observed_max_ts

                    if len(batch_rows) >= resolved_db_batch_rows:
                        total_rows = _commit_candle_batch(
                            batch_rows,
                            batch_last_ts,
                            symbols=normalized_symbols,
                            last_ts_by_symbol=last_ts_by_symbol,
                            total_rows=total_rows,
                            chunk_index=chunk_index,
                            chunk_rows=chunk_rows,
                            requested_start_ts=requested_start_ts,
                            requested_end_ts=requested_end_ts,
                            dataset_revision=dataset_revision,
                        )
                        batch_rows = []
                        batch_last_ts = {}

                total_rows = _commit_candle_batch(
                    batch_rows,
                    batch_last_ts,
                    symbols=normalized_symbols,
                    last_ts_by_symbol=last_ts_by_symbol,
                    total_rows=total_rows,
                    chunk_index=chunk_index,
                    chunk_rows=chunk_rows,
                    requested_start_ts=requested_start_ts,
                    requested_end_ts=requested_end_ts,
                    dataset_revision=dataset_revision,
                )

            indicator_rows = 0
            if resolved_with_indicators:
                indicator_rows = run_historical_backfill(
                    symbols=normalized_symbols,
                    intervals=indicator_intervals,
                    start_ts=requested_start_ts,
                    end_ts=requested_end_ts,
                    resume=resume,
                )

            _write_backfill_state(
                normalized_symbols,
                last_ts_by_symbol=last_ts_by_symbol,
                status="done",
                error_message=None,
                scan_chunk_index=current_scan_chunk_index,
                chunk_rows=chunk_rows,
                requested_start_ts=requested_start_ts,
                requested_end_ts=requested_end_ts,
                rows_written=total_rows,
                dataset_revision=dataset_revision,
            )
            state_store.heartbeat(
                "backfill",
                status="running",
                message=f"rows={total_rows} indicators={indicator_rows} latest={observed_max_ts}",
            )
            LOG.info(
                "backfill done rows=%s indicator_rows=%s symbols=%s latest=%s",
                total_rows,
                indicator_rows,
                len(normalized_symbols),
                observed_max_ts,
            )
    except Exception as exc:  # noqa: BLE001
        error_message = _truncate_error(exc)
        _write_backfill_state(
            normalized_symbols,
            last_ts_by_symbol=last_ts_by_symbol,
            status="error",
            error_message=error_message,
            scan_chunk_index=current_scan_chunk_index,
            chunk_rows=chunk_rows,
            requested_start_ts=requested_start_ts,
            requested_end_ts=requested_end_ts,
            rows_written=total_rows,
            dataset_revision=dataset_revision,
        )
        state_store.heartbeat("backfill", status="degraded", message=error_message)
        raise
