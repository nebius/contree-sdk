from __future__ import annotations

import json
import threading
import time
from asyncio import Lock
from typing import Any

from contree_sdk.cache.base import AsyncCache, SyncCache
from contree_sdk.cache.models import CacheEntry, Clock, expiration


class SyncMemoryCache(SyncCache):
    """In-process JSON cache with a caller-replaceable wall clock."""

    def __init__(self, *, clock: Clock = time.time) -> None:
        self.records: dict[tuple[str, str], tuple[str, float | None]] = {}
        self.clock = clock
        self.lock = threading.Lock()

    def get_entry(self, key: str, *, namespace: str = "default") -> CacheEntry | None:
        with self.lock:
            record = self.records.get((namespace, key))
            if record is None or (record[1] is not None and record[1] <= self.clock()):
                return None
            return CacheEntry(key, json.loads(record[0]), record[1])

    def set(self, key: str, value: Any, *, namespace: str = "default", ttl: float | None = None) -> None:
        encoded = json.dumps(value, allow_nan=False)
        expires_at = expiration(ttl, self.clock())
        with self.lock:
            self.records[namespace, key] = (encoded, expires_at)

    def entries(self, *, namespace: str = "default", prefix: str = "") -> tuple[CacheEntry, ...]:
        with self.lock:
            now = self.clock()
            return tuple(
                CacheEntry(key, json.loads(value), expires_at)
                for (space, key), (value, expires_at) in sorted(self.records.items())
                if space == namespace and key.startswith(prefix) and (expires_at is None or expires_at > now)
            )

    def delete(self, key: str, *, namespace: str = "default") -> bool:
        with self.lock:
            return self.records.pop((namespace, key), None) is not None

    def invalidate(self, *, namespace: str = "default", prefix: str = "") -> int:
        with self.lock:
            keys = [item for item in self.records if item[0] == namespace and item[1].startswith(prefix)]
            for key in keys:
                del self.records[key]
            return len(keys)


class AsyncMemoryCache(AsyncCache):
    """In-process JSON cache with a caller-replaceable wall clock."""

    def __init__(self, *, clock: Clock = time.time) -> None:
        self.records: dict[tuple[str, str], tuple[str, float | None]] = {}
        self.clock = clock
        self.lock = Lock()

    async def get_entry(self, key: str, *, namespace: str = "default") -> CacheEntry | None:
        async with self.lock:
            record = self.records.get((namespace, key))
            if record is None or (record[1] is not None and record[1] <= self.clock()):
                return None
            return CacheEntry(key, json.loads(record[0]), record[1])

    async def set(self, key: str, value: Any, *, namespace: str = "default", ttl: float | None = None) -> None:
        encoded = json.dumps(value, allow_nan=False)
        expires_at = expiration(ttl, self.clock())
        async with self.lock:
            self.records[namespace, key] = (encoded, expires_at)

    async def entries(self, *, namespace: str = "default", prefix: str = "") -> tuple[CacheEntry, ...]:
        async with self.lock:
            now = self.clock()
            return tuple(
                CacheEntry(key, json.loads(value), expires_at)
                for (space, key), (value, expires_at) in sorted(self.records.items())
                if space == namespace and key.startswith(prefix) and (expires_at is None or expires_at > now)
            )

    async def delete(self, key: str, *, namespace: str = "default") -> bool:
        async with self.lock:
            return self.records.pop((namespace, key), None) is not None

    async def invalidate(self, *, namespace: str = "default", prefix: str = "") -> int:
        async with self.lock:
            keys = [item for item in self.records if item[0] == namespace and item[1].startswith(prefix)]
            for key in keys:
                del self.records[key]
            return len(keys)
