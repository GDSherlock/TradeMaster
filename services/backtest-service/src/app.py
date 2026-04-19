from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .auth import enforce_http_auth
from .catalog import build_catalog
from .config import settings
from .db import db, interval_seconds
from .dsl import DslValidationError, normalize_dsl
from .response import ErrorCode, api_response, error_response


class InMemoryRateLimiter:
    def __init__(self, read_rate: int, read_burst: int, write_rate: int, write_burst: int) -> None:
        self.read_rate = max(1, read_rate)
        self.read_burst = max(1, read_burst)
        self.write_rate = max(1, write_rate)
        self.write_burst = max(1, write_burst)
        self._lock = threading.Lock()
        self._tokens: dict[str, tuple[float, float]] = {}

    def allow(self, key: str, write: bool) -> bool:
        now = time.time()
        rate = self.write_rate if write else self.read_rate
        burst = self.write_burst if write else self.read_burst
        scoped_key = f"{'write' if write else 'read'}:{key}"
        with self._lock:
            tokens, ts = self._tokens.get(scoped_key, (float(burst), now))
            refill = (now - ts) * (rate / 60.0)
            tokens = min(float(burst), tokens + max(0.0, refill))
            if tokens < 1:
                self._tokens[scoped_key] = (tokens, now)
                return False
            self._tokens[scoped_key] = (tokens - 1, now)
            return True


limiter = InMemoryRateLimiter(
    settings.rate_limit_per_minute,
    settings.rate_limit_burst,
    settings.write_rate_limit_per_minute,
    settings.write_rate_limit_burst,
)

app = FastAPI(title="TradeMaster Backtest Service", version=__version__, docs_url="/docs", redoc_url="/redoc")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.middleware("http")
async def auth_and_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    try:
        enforce_http_auth(request)
    except Exception:
        return JSONResponse(status_code=401, content=error_response(ErrorCode.UNAUTHORIZED, "unauthorized"))

    if request.url.path not in {"/backtest/health", "/docs", "/openapi.json", "/redoc"}:
        is_write = request.method.upper() == "POST"
        if not limiter.allow(client_ip, write=is_write):
            return JSONResponse(status_code=429, content=error_response(ErrorCode.RATE_LIMITED, "rate limited"))

    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError):
    msg = exc.errors()[0].get("msg", "invalid parameters") if exc.errors() else "invalid parameters"
    return JSONResponse(status_code=400, content=error_response(ErrorCode.PARAM_ERROR, msg))


@app.exception_handler(DslValidationError)
async def dsl_exception_handler(_: Request, exc: DslValidationError):
    return JSONResponse(status_code=400, content=error_response(ErrorCode.PARAM_ERROR, str(exc)))


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    if exc.status_code == 404:
        return JSONResponse(status_code=404, content=error_response(ErrorCode.NOT_FOUND, "not found"))
    return JSONResponse(status_code=exc.status_code, content=error_response(ErrorCode.PARAM_ERROR, "invalid request"))


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    return JSONResponse(status_code=500, content=error_response(ErrorCode.INTERNAL_ERROR, "internal server error"))


def _parse_iso_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DslValidationError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_window(interval: str, start_ts: datetime, end_ts: datetime) -> None:
    if end_ts <= start_ts:
        raise DslValidationError("end_ts must be after start_ts")
    expected_bars = int((end_ts - start_ts).total_seconds() / interval_seconds(interval))
    if expected_bars <= 0:
        raise DslValidationError("window must cover at least one bar")
    if expected_bars > settings.max_bars_per_run:
        raise DslValidationError("window exceeds BACKTEST_MAX_BARS_PER_RUN")


@app.get("/backtest/health")
def health() -> dict:
    return {
        "status": "healthy",
        "service": "backtest-service",
        "version": __version__,
        "timestamp": int(datetime.now(tz=timezone.utc).timestamp() * 1000),
    }


@app.get("/backtest/catalog")
def backtest_catalog() -> dict:
    return api_response(
        build_catalog(
            symbols=db.list_symbols(settings.default_exchange),
            supported_intervals=settings.supported_intervals,
            signal_rules=db.list_signal_rules(),
        )
    )


@app.get("/backtest/strategies")
def list_strategies() -> dict:
    return api_response(db.list_strategies())


@app.post("/backtest/strategies")
async def create_strategy(request: Request) -> dict:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise DslValidationError("payload must be an object")

    name = str(payload.get("name", "")).strip()
    if not name:
        raise DslValidationError("name is required")

    description = str(payload.get("description", "")).strip()
    exchange = str(payload.get("exchange") or settings.default_exchange).strip() or settings.default_exchange
    symbol = str(payload.get("symbol", "")).strip().upper()
    interval = str(payload.get("interval", "")).strip().lower()
    if not symbol:
        raise DslValidationError("symbol is required")
    if interval not in settings.supported_intervals:
        raise DslValidationError("interval is not supported")

    dsl = normalize_dsl(payload.get("dsl"))
    strategy_id = payload.get("strategy_id")
    if strategy_id is not None:
        try:
            strategy_id = int(strategy_id)
        except (TypeError, ValueError):
            raise DslValidationError("strategy_id must be an integer") from None

    try:
        result = db.create_strategy_version(
            name=name,
            description=description,
            exchange=exchange,
            symbol=symbol,
            interval=interval,
            dsl=dsl,
            strategy_id=strategy_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404) from exc
    return api_response(result)


@app.get("/backtest/strategies/{strategy_id}")
def get_strategy(strategy_id: int) -> dict:
    strategy = db.get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404)
    return api_response(strategy)


@app.get("/backtest/strategies/{strategy_id}/versions")
def list_strategy_versions(strategy_id: int) -> dict:
    strategy = db.get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404)
    return api_response(db.list_strategy_versions(strategy_id))


@app.post("/backtest/runs")
async def create_run(request: Request) -> dict:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise DslValidationError("payload must be an object")

    try:
        strategy_version_id = int(payload.get("strategy_version_id"))
    except (TypeError, ValueError):
        raise DslValidationError("strategy_version_id is required") from None

    strategy_version = db.get_strategy_version(strategy_version_id)
    if not strategy_version:
        raise HTTPException(status_code=404)

    exchange = str(payload.get("exchange") or strategy_version["exchange"]).strip() or strategy_version["exchange"]
    symbol = str(payload.get("symbol") or strategy_version["symbol"]).strip().upper()
    interval = str(payload.get("interval") or strategy_version["interval"]).strip().lower()
    if interval not in settings.supported_intervals:
        raise DslValidationError("interval is not supported")
    start_ts = _parse_iso_timestamp(str(payload.get("start_ts", "")), "start_ts")
    end_ts = _parse_iso_timestamp(str(payload.get("end_ts", "")), "end_ts")
    _validate_window(interval, start_ts, end_ts)
    initial_equity = float(payload.get("initial_equity") or settings.initial_equity)
    if initial_equity <= 0:
        raise DslValidationError("initial_equity must be > 0")

    run_params = {
        "exchange": exchange,
        "symbol": symbol,
        "interval": interval,
        "start_ts": start_ts.isoformat(),
        "end_ts": end_ts.isoformat(),
        "initial_equity": initial_equity,
        "fill_policy": strategy_version["dsl"]["execution"]["fill_policy"],
    }
    run = db.create_run(strategy_version, exchange, symbol, interval, start_ts, end_ts, run_params)
    return api_response(run)


@app.get("/backtest/runs")
def list_runs(limit: int = Query(default=100, ge=1, le=200)) -> dict:
    return api_response(db.list_runs(limit=limit))


@app.get("/backtest/runs/{run_id}")
def get_run(run_id: int) -> dict:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404)
    return api_response(run)


@app.get("/backtest/runs/{run_id}/equity")
def get_run_equity(run_id: int, response: Response) -> dict:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404)
    response.headers["Cache-Control"] = "public,max-age=2"
    return api_response(db.get_run_equity(run_id))


@app.get("/backtest/runs/{run_id}/trades")
def get_run_trades(run_id: int, response: Response) -> dict:
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404)
    response.headers["Cache-Control"] = "public,max-age=2"
    return api_response(db.get_run_trades(run_id))


@app.post("/backtest/runs/{run_id}/cancel")
def cancel_run(run_id: int) -> dict:
    run = db.cancel_run(run_id)
    if not run:
        raise HTTPException(status_code=404)
    return api_response(run)
