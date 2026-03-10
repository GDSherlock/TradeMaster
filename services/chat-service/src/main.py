from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import settings
from .context_builder import build_context
from .guardrails import redact_sensitive, validate_message
from .provider import call_llm
from .rate_limit import ChatLimiter
from .render_payload import (
    build_fallback_draft,
    build_prompt,
    build_render_payload,
    detect_language,
    format_plain_reply,
    infer_confidence,
    infer_data_quality,
    infer_stance,
    normalize_mode,
    validate_model_draft,
)

app = FastAPI(title="TradeCat MVP Chat Service", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

limiter = ChatLimiter(settings.rate_limit_per_minute, settings.max_concurrency_per_ip)
sessions: dict[str, list[dict[str, str]]] = {}


class ChatHistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class ChatUIContext(BaseModel):
    symbol: str | None = Field(default=None, min_length=2, max_length=20, pattern=r"^[A-Za-z0-9]{2,20}(USDT)?$")
    interval: Literal["1m", "5m", "15m", "1h", "4h", "1d"] | None = None
    active_rule: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9:_-]+$")
    ml_decision: Literal["pending", "passed", "review", "rejected", "unavailable"] | None = None
    requested_mode: Literal["compact", "standard", "deep"] | None = None
    language: Literal["en", "zh"] | None = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: str | None = None
    history: list[ChatHistoryItem] | None = None
    ui_context: ChatUIContext | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    model: str
    timestamp_ms: int
    render_payload: dict[str, Any] | None = None
    schema_version: str | None = None
    mode: str | None = None
    degraded_reason: str | None = None


def _now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


def _ip_hash(ip: str) -> str:
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]


def _audit_file(entry: dict[str, Any]) -> None:
    path = Path(settings.audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _audit_db(entry: dict[str, Any]) -> None:
    if not settings.database_url:
        return
    sql = """
    INSERT INTO audit.chat_requests (
      request_id, session_id, user_hash, symbol, interval, status,
      latency_ms, tokens_in, tokens_out, model, error_message
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(
            sql,
            (
                entry.get("request_id"),
                entry.get("session_id"),
                entry.get("user_hash"),
                entry.get("symbol"),
                entry.get("interval"),
                entry.get("status"),
                entry.get("latency_ms"),
                entry.get("tokens_in"),
                entry.get("tokens_out"),
                entry.get("model"),
                entry.get("error_message"),
            ),
        )
        conn.commit()


def _save_audit(entry: dict[str, Any]) -> None:
    _audit_file(entry)
    try:
        _audit_db(entry)
    except Exception:  # noqa: BLE001
        pass


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "service": "chat-service",
        "model": settings.llm_model,
        "timestamp": _now_ms(),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, request: Request) -> ChatResponse:
    request_id = uuid.uuid4().hex
    session_id = req.session_id or uuid.uuid4().hex
    ip = request.client.host if request.client else "unknown"

    if not limiter.acquire(ip):
        raise HTTPException(status_code=429, detail="rate limited")

    started = time.time()
    status = "ok"
    context: dict[str, Any] = {}
    error_message = None
    reply = ""
    degraded_reason = None

    try:
        valid, reason = validate_message(req.message, settings.max_input_chars)
        if not valid:
            raise HTTPException(status_code=400, detail=reason)

        ui_context = req.ui_context.model_dump(exclude_none=True) if req.ui_context else {}
        context = await build_context(req.message, ui_context)

        history_items = req.history if req.history is not None else sessions.get(session_id, [])
        history: list[dict[str, str]] = []
        for item in history_items:
            if isinstance(item, ChatHistoryItem):
                history.append({"role": item.role, "content": item.content})
                continue
            if isinstance(item, dict) and item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str):
                history.append({"role": str(item["role"]), "content": str(item["content"])[:4000]})
        history = history[- settings.max_turns * 2 :]

        mode = normalize_mode(ui_context.get("requested_mode"))
        language = detect_language(req.message, ui_context.get("language"))
        data_quality = infer_data_quality(context, language)
        stance = infer_stance(context, req.message)
        confidence = infer_confidence(context, stance, data_quality, language)
        system_prompt = build_prompt(
            context=context,
            message=req.message,
            mode=mode,
            language=language,
            stance=stance,
            confidence=confidence,
            data_quality=data_quality,
        )

        conversation = history + [{"role": "user", "content": req.message}]
        messages = [{"role": "system", "content": system_prompt}] + conversation

        raw_reply = await call_llm(messages)
        draft = validate_model_draft(raw_reply, mode)
        if draft is None:
            degraded_reason = "structured_response_unavailable"
            draft = build_fallback_draft(
                context=context,
                mode=mode,
                language=language,
                stance=stance,
                confidence=confidence,
            )

        render_payload = build_render_payload(
            draft=draft,
            context=context,
            mode=mode,
            language=language,
            stance=stance,
            confidence=confidence,
            data_quality=data_quality,
        )
        reply = format_plain_reply(render_payload)
        conversation.append({"role": "assistant", "content": reply})
        sessions[session_id] = conversation[- settings.max_turns * 2 :]

        return ChatResponse(
            reply=reply,
            session_id=session_id,
            model=settings.llm_model,
            timestamp_ms=_now_ms(),
            render_payload=render_payload.model_dump(exclude_none=True),
            schema_version=render_payload.version,
            mode=render_payload.mode,
            degraded_reason=degraded_reason,
        )
    except HTTPException as exc:
        status = "error"
        error_message = str(exc.detail)
        raise
    except Exception as exc:  # noqa: BLE001
        status = "error"
        error_message = str(exc)
        raise HTTPException(status_code=500, detail="chat failed") from exc
    finally:
        limiter.release(ip)
        latency_ms = int((time.time() - started) * 1000)
        entry = {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "request_id": request_id,
            "session_id": session_id,
            "user_hash": _ip_hash(ip),
            "symbol": context.get("symbol"),
            "interval": context.get("interval"),
            "status": status,
            "latency_ms": latency_ms,
            "tokens_in": len(req.message),
            "tokens_out": len(reply),
            "model": settings.llm_model,
            "error_message": redact_sensitive(error_message or ""),
        }
        _save_audit(entry)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host=settings.host, port=settings.port, log_level="info")
