from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from contree_sdk.cache.models import CacheEntry
from contree_sdk.compat import Self


class SyncCache(ABC):
    """A sync JSON cache with explicit namespaces, expiration, and invalidation.

    Every key lives within a `namespace` (default `"default"`), so unrelated
    callers keying by e.g. a bare URL or a sha256 digest can't collide with
    each other even if the raw key string happens to match.
    """

    def get(self, key: str, *, namespace: str = "default") -> Any | None:
        entry = self.get_entry(key, namespace=namespace)
        return None if entry is None else entry.value

    @abstractmethod
    def get_entry(self, key: str, *, namespace: str = "default") -> CacheEntry | None:
        """Read a detached live record; return None for a missing or expired key."""

    @abstractmethod
    def set(self, key: str, value: Any, *, namespace: str = "default", ttl: float | None = None) -> None:
        """Store JSON data for ttl seconds; None never expires, zero expires immediately."""

    @abstractmethod
    def entries(self, *, namespace: str = "default", prefix: str = "") -> tuple[CacheEntry, ...]:
        """Read live records in key order. Prefix matching is literal."""

    @abstractmethod
    def delete(self, key: str, *, namespace: str = "default") -> bool:
        """Remove a stored key, including expired records; return whether it existed."""

    @abstractmethod
    def invalidate(self, *, namespace: str = "default", prefix: str = "") -> int:
        """Remove matching stored keys atomically, including expired records; return their count."""

    def close(self) -> None:  # noqa: B027 - public extension contract
        """Release owned resources. The default implementation has no resources."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


class AsyncCache(ABC):
    """A native async JSON cache with explicit namespaces and expiration.

    Every key lives within a `namespace` (default `"default"`), so unrelated
    callers keying by e.g. a bare URL or a sha256 digest can't collide with
    each other even if the raw key string happens to match.
    """

    async def get(self, key: str, *, namespace: str = "default") -> Any | None:
        entry = await self.get_entry(key, namespace=namespace)
        return None if entry is None else entry.value

    @abstractmethod
    async def get_entry(self, key: str, *, namespace: str = "default") -> CacheEntry | None:
        """Read a detached live record; return None for a missing or expired key."""

    @abstractmethod
    async def set(self, key: str, value: Any, *, namespace: str = "default", ttl: float | None = None) -> None:
        """Store JSON data for ttl seconds; None never expires, zero expires immediately."""

    @abstractmethod
    async def entries(self, *, namespace: str = "default", prefix: str = "") -> tuple[CacheEntry, ...]:
        """Read live records in key order. Prefix matching is literal."""

    @abstractmethod
    async def delete(self, key: str, *, namespace: str = "default") -> bool:
        """Remove a stored key, including expired records; return whether it existed."""

    @abstractmethod
    async def invalidate(self, *, namespace: str = "default", prefix: str = "") -> int:
        """Remove matching stored keys atomically, including expired records; return their count."""

    async def close(self) -> None:  # noqa: B027 - public extension contract
        """Release owned resources. The default implementation has no resources."""

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()
