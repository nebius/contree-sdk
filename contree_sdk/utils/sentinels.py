from __future__ import annotations

from types import EllipsisType
from typing import TypeVar


T = TypeVar("T")


def value_or_none(value: T | EllipsisType) -> T | None:
    """Collapse `contree_client`'s `...` ("field omitted") sentinel to `None`.

    Returns:
        `value` unchanged, or `None` if `value` is the `...` sentinel.

    """
    return None if isinstance(value, EllipsisType) else value
