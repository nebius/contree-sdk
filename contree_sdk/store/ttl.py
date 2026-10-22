"""Expiration helpers for local stores and upload reuse."""

from collections.abc import Callable
from math import isfinite


Clock = Callable[[], float]


def expiration(ttl: float | None, now: float) -> float | None:
    if ttl is None:
        return None
    if not isfinite(ttl) or ttl < 0:
        raise ValueError("ttl must be finite and nonnegative")
    expires_at = now + ttl
    if not isfinite(expires_at):
        raise ValueError("expiration must be finite")
    return expires_at
