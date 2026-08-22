from __future__ import annotations

import threading
from asyncio import Lock
from typing import Any

from contree_sdk.cache.base import AsyncCache, SyncCache


class SyncMemoryCache(SyncCache):
    """Pure in-process Cache: a plain dict guarded by a threading.Lock."""

    def __init__(self) -> None:
        self.entries: dict[str, Any] = {}
        self.lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self.lock:
            return self.entries.get(key)

    def set(self, key: str, value: Any) -> None:
        with self.lock:
            self.entries[key] = value


class AsyncMemoryCache(AsyncCache):
    """Pure in-process Cache: a plain dict guarded by an asyncio.Lock."""

    def __init__(self) -> None:
        self.entries: dict[str, Any] = {}
        self.lock = Lock()

    async def get(self, key: str) -> Any | None:
        async with self.lock:
            return self.entries.get(key)

    async def set(self, key: str, value: Any) -> None:
        async with self.lock:
            self.entries[key] = value
