"""Cache records and clock-based expiration."""

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from typing import Any


Clock = Callable[[], float]


@dataclass(frozen=True)
class CacheEntry:
    key: str
    value: Any
    expires_at: float | None = None


def expiration(ttl: float | None, now: float) -> float | None:
    if ttl is None:
        return None
    if not isfinite(ttl) or ttl < 0:
        raise ValueError("ttl must be finite and nonnegative")
    expires_at = now + ttl
    if not isfinite(expires_at):
        raise ValueError("expiration must be finite")
    return expires_at
