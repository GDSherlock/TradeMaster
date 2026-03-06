from __future__ import annotations

from datetime import datetime
from typing import Any

from .config import settings
from .storage import Storage


class StateStore:
    def __init__(self, db: Storage) -> None:
        self.db = db

    def get_backfill_state(self, source: str, symbol: str, interval: str) -> dict[str, Any] | None:
        sql = """
        SELECT source, symbol, interval, last_ts, status, error_message,
               scan_chunk_index, chunk_rows, requested_start_ts, requested_end_ts,
               rows_written, dataset_revision, updated_at
        FROM market_data.backfill_state
        WHERE source = %s AND symbol = %s AND interval = %s
        """
        with self.db.pool.connection() as conn:
            row = conn.execute(sql, (source, symbol, interval)).fetchone()
        return dict(row) if row else None

    def get_backfill_last_ts(self, source: str, symbol: str, interval: str) -> datetime | None:
        row = self.get_backfill_state(source, symbol, interval)
        return row["last_ts"] if row else None

    def set_backfill_state(
        self,
        source: str,
        symbol: str,
        interval: str,
        last_ts: datetime | None,
        status: str,
        error_message: str | None = None,
        scan_chunk_index: int | None = None,
        chunk_rows: int | None = None,
        requested_start_ts: datetime | None = None,
        requested_end_ts: datetime | None = None,
        rows_written: int | None = None,
        dataset_revision: str | None = None,
    ) -> None:
        sql = """
        INSERT INTO market_data.backfill_state (
            source, symbol, interval, last_ts, status, error_message,
            scan_chunk_index, chunk_rows, requested_start_ts, requested_end_ts,
            rows_written, dataset_revision, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT (source, symbol, interval)
        DO UPDATE SET last_ts = EXCLUDED.last_ts,
                      status = EXCLUDED.status,
                      error_message = EXCLUDED.error_message,
                      scan_chunk_index = EXCLUDED.scan_chunk_index,
                      chunk_rows = EXCLUDED.chunk_rows,
                      requested_start_ts = EXCLUDED.requested_start_ts,
                      requested_end_ts = EXCLUDED.requested_end_ts,
                      rows_written = EXCLUDED.rows_written,
                      dataset_revision = EXCLUDED.dataset_revision,
                      updated_at = NOW();
        """
        with self.db.pool.connection() as conn:
            conn.execute(
                sql,
                (
                    source,
                    symbol,
                    interval,
                    last_ts,
                    status,
                    error_message,
                    scan_chunk_index,
                    chunk_rows,
                    requested_start_ts,
                    requested_end_ts,
                    rows_written,
                    dataset_revision,
                ),
            )
            conn.commit()

    def get_indicator_last_ts(self, exchange: str, symbol: str, interval: str) -> datetime | None:
        sql = """
        SELECT last_processed_ts
        FROM market_data.indicator_state
        WHERE exchange = %s AND symbol = %s AND interval = %s
        """
        with self.db.pool.connection() as conn:
            row = conn.execute(sql, (exchange, symbol, interval)).fetchone()
        return row["last_processed_ts"] if row else None

    def set_indicator_last_ts(self, exchange: str, symbol: str, interval: str, ts: datetime | None) -> None:
        sql = """
        INSERT INTO market_data.indicator_state (exchange, symbol, interval, last_processed_ts, updated_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (exchange, symbol, interval)
        DO UPDATE SET last_processed_ts = EXCLUDED.last_processed_ts,
                      updated_at = NOW();
        """
        with self.db.pool.connection() as conn:
            conn.execute(sql, (exchange, symbol, interval, ts))
            conn.commit()

    def heartbeat(self, component: str, status: str = "running", message: str | None = None) -> None:
        sql = """
        INSERT INTO market_data.ingest_heartbeat (component, last_seen_at, status, message)
        VALUES (%s, NOW(), %s, %s)
        ON CONFLICT (component)
        DO UPDATE SET last_seen_at = NOW(), status = EXCLUDED.status, message = EXCLUDED.message;
        """
        with self.db.pool.connection() as conn:
            conn.execute(sql, (component, status, message))
            conn.commit()


state_store = StateStore(db=Storage(settings.database_url))
