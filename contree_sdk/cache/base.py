from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SyncCache(ABC):
    """A minimal sync key/value cache: get returns None on a miss, set overwrites."""

    @abstractmethod
    def get(self, key: str) -> Any | None: ...

    @abstractmethod
    def set(self, key: str, value: Any) -> None: ...


class AsyncCache(ABC):
    """A minimal async key/value cache: get returns None on a miss, set overwrites."""

    @abstractmethod
    async def get(self, key: str) -> Any | None: ...

    @abstractmethod
    async def set(self, key: str, value: Any) -> None: ...
