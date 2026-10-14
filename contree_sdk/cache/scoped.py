"""Bind cache namespaces to a server and an authorization context."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from contree_client.types import ContreeAsyncClient, ContreeSyncClient

from contree_sdk.cache.base import AsyncCache, SyncCache
from contree_sdk.cache.models import CacheEntry


@dataclass(frozen=True)
class CacheScope:
    """A non-secret digest separating endpoint, project, credential, and profile."""

    digest: str

    @classmethod
    def from_client(cls, client: ContreeSyncClient | ContreeAsyncClient, *, profile: str = "") -> CacheScope:
        """Derive a scope without storing credentials in cache keys or records.

        Returns:
            A scope that changes when endpoint, project, credential, or profile changes.

        """
        parts = [client.base_url.rstrip("/"), client.project, client.token, profile]
        return cls(hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest())

    def namespace(self, name: str) -> str:
        return json.dumps(["contree-sdk", self.digest, name], separators=(",", ":"))


class ScopedSyncCache(SyncCache):
    """A namespace view over a caller-owned cache. Closing the view does not close its cache."""

    def __init__(self, cache: SyncCache, scope: CacheScope) -> None:
        self.cache = cache
        self.scope = scope

    def get_entry(self, key: str, *, namespace: str = "default") -> CacheEntry | None:
        return self.cache.get_entry(key, namespace=self.scope.namespace(namespace))

    def set(self, key: str, value: Any, *, namespace: str = "default", ttl: float | None = None) -> None:
        self.cache.set(key, value, namespace=self.scope.namespace(namespace), ttl=ttl)

    def entries(self, *, namespace: str = "default", prefix: str = "") -> tuple[CacheEntry, ...]:
        return self.cache.entries(namespace=self.scope.namespace(namespace), prefix=prefix)

    def delete(self, key: str, *, namespace: str = "default") -> bool:
        return self.cache.delete(key, namespace=self.scope.namespace(namespace))

    def invalidate(self, *, namespace: str = "default", prefix: str = "") -> int:
        return self.cache.invalidate(namespace=self.scope.namespace(namespace), prefix=prefix)


class ScopedAsyncCache(AsyncCache):
    """Native asynchronous namespace view over a caller-owned cache."""

    def __init__(self, cache: AsyncCache, scope: CacheScope) -> None:
        self.cache = cache
        self.scope = scope

    async def get_entry(self, key: str, *, namespace: str = "default") -> CacheEntry | None:
        return await self.cache.get_entry(key, namespace=self.scope.namespace(namespace))

    async def set(self, key: str, value: Any, *, namespace: str = "default", ttl: float | None = None) -> None:
        await self.cache.set(key, value, namespace=self.scope.namespace(namespace), ttl=ttl)

    async def entries(self, *, namespace: str = "default", prefix: str = "") -> tuple[CacheEntry, ...]:
        return await self.cache.entries(namespace=self.scope.namespace(namespace), prefix=prefix)

    async def delete(self, key: str, *, namespace: str = "default") -> bool:
        return await self.cache.delete(key, namespace=self.scope.namespace(namespace))

    async def invalidate(self, *, namespace: str = "default", prefix: str = "") -> int:
        return await self.cache.invalidate(namespace=self.scope.namespace(namespace), prefix=prefix)
