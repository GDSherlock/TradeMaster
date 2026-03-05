from __future__ import annotations

import re

INJECTION_PATTERNS = [
    r"ignore\s+previous\s+instructions",
    r"reveal\s+system\s+prompt",
    r"print\s+api\s*key",
    r"leak\s+token",
    r"<script",
]

SENSITIVE_PATTERNS = [
    r"sk-[A-Za-z0-9_-]{10,}",
    r"Bearer\s+[A-Za-z0-9._-]+",
    r"token=[A-Za-z0-9._-]+",
]


def validate_message(message: str, max_chars: int) -> tuple[bool, str]:
    text = message.strip()
    if not text:
        return False, "empty message"
    if len(text) > max_chars:
        return False, f"message too long, max={max_chars}"

    lowered = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            return False, "possible prompt injection detected"
    return True, "ok"


def redact_sensitive(text: str) -> str:
    out = text
    for pattern in SENSITIVE_PATTERNS:
        out = re.sub(pattern, "[REDACTED]", out, flags=re.IGNORECASE)
    return out
