from __future__ import annotations

from typing import Any

import httpx

from .config import settings


def _extract_reply(payload: dict[str, Any]) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            msg = first.get("message")
            if isinstance(msg, dict) and msg.get("content"):
                return str(msg["content"])
            if first.get("text"):
                return str(first["text"])
    output = payload.get("output")
    if isinstance(output, list) and output:
        content = output[0].get("content") if isinstance(output[0], dict) else None
        if isinstance(content, list) and content and content[0].get("text"):
            return str(content[0]["text"])
    return "No reply content found."


async def call_llm(messages: list[dict[str, str]]) -> str:
    if not settings.llm_api_key:
        return "LLM_API_KEY is not configured."

    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    base = settings.llm_base_url.rstrip("/")
    timeout = settings.llm_timeout_seconds

    # Try Responses API first
    responses_url = f"{base}/responses" if not base.endswith("/v1") else f"{base}/responses"
    responses_payload = {
        "model": settings.llm_model,
        "input": [
            {
                "role": m["role"],
                "content": [{"type": "input_text", "text": m["content"]}],
            }
            for m in messages
        ],
        "temperature": settings.temperature,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(responses_url, headers=headers, json=responses_payload)
            if resp.is_success:
                return _extract_reply(resp.json())[: settings.llm_max_output_chars]
        except Exception:  # noqa: BLE001
            pass

        # Fallback to chat completions
        chat_url = f"{base}/chat/completions" if not base.endswith("/v1") else f"{base}/chat/completions"
        chat_payload = {
            "model": settings.llm_model,
            "messages": messages,
            "temperature": settings.temperature,
        }
        resp = await client.post(chat_url, headers=headers, json=chat_payload)
        resp.raise_for_status()
        return _extract_reply(resp.json())[: settings.llm_max_output_chars]
