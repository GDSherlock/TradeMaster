from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheItem:
    expire_at: float
    data: Any
    etag: str


class TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, CacheItem] = {}

    def get(self, key: str) -> CacheItem | None:
        item = self._store.get(key)
        if item is None:
            return None
        if item.expire_at < time.time():
            self._store.pop(key, None)
            return None
        return item

    def set(self, key: str, data: Any, ttl_seconds: int) -> CacheItem:
        payload = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
        etag = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
        item = CacheItem(expire_at=time.time() + ttl_seconds, data=data, etag=etag)
        self._store[key] = item
        return item


cache = TTLCache()
