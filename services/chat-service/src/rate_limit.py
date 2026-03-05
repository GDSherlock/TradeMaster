from __future__ import annotations

import threading
import time


class ChatLimiter:
    def __init__(self, per_minute: int, max_concurrency: int) -> None:
        self.per_minute = max(1, per_minute)
        self.max_concurrency = max(1, max_concurrency)
        self._lock = threading.Lock()
        self._bucket: dict[str, tuple[float, float]] = {}
        self._inflight: dict[str, int] = {}

    def acquire(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            inflight = self._inflight.get(key, 0)
            if inflight >= self.max_concurrency:
                return False

            tokens, ts = self._bucket.get(key, (float(self.per_minute), now))
            tokens += (now - ts) * (self.per_minute / 60.0)
            tokens = min(float(self.per_minute), tokens)
            if tokens < 1:
                self._bucket[key] = (tokens, now)
                return False

            tokens -= 1
            self._bucket[key] = (tokens, now)
            self._inflight[key] = inflight + 1
            return True

    def release(self, key: str) -> None:
        with self._lock:
            inflight = self._inflight.get(key, 0)
            if inflight <= 1:
                self._inflight.pop(key, None)
            else:
                self._inflight[key] = inflight - 1
