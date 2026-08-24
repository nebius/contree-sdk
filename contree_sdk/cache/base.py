from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SyncCache(ABC):
    """A minimal sync key/value cache: get returns None on a miss, set overwrites.

    Every key lives within a `namespace` (default `"default"`), so unrelated
    callers keying by e.g. a bare URL or a sha256 digest can't collide with
    each other even if the raw key string happens to match.
    """

    @abstractmethod
    def get(self, key: str, *, namespace: str = "default") -> Any | None: ...

    @abstractmethod
    def set(self, key: str, value: Any, *, namespace: str = "default") -> None: ...


class AsyncCache(ABC):
    """A minimal async key/value cache: get returns None on a miss, set overwrites.

    Every key lives within a `namespace` (default `"default"`), so unrelated
    callers keying by e.g. a bare URL or a sha256 digest can't collide with
    each other even if the raw key string happens to match.
    """

    @abstractmethod
    async def get(self, key: str, *, namespace: str = "default") -> Any | None: ...

    @abstractmethod
    async def set(self, key: str, value: Any, *, namespace: str = "default") -> None: ...
