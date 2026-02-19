from collections.abc import Callable
from functools import wraps
from inspect import signature
from typing import Any, ParamSpec, TypeVar


P = ParamSpec("P")
R = TypeVar("R")


def keep_signature(original_func: Callable[P, Any]) -> Callable[[Callable[..., R]], Callable[P, R]]:

    def decorator(func: Callable[..., R]) -> Callable[P, R]:
        wrapped = wraps(original_func)(func)
        wrapped.__name__ = func.__name__
        wrapped.__qualname__ = func.__qualname__
        wrapped.__signature__ = signature(original_func)  # type: ignore[reportAttributeAccessIssue]
        return wrapped

    return decorator
