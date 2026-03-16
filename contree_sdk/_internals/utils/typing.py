from collections.abc import Callable
from functools import wraps
from inspect import signature
from typing import Any, ParamSpec, TypeVar, overload


__all__ = [
    "keep_signature",
]

P = ParamSpec("P")
R = TypeVar("R")
F = TypeVar("F", bound=Callable[..., Any])


@overload
def keep_signature(original_func: Callable[P, Any]) -> Callable[[Callable[..., R]], Callable[P, R]]: ...
@overload
def keep_signature(original_func: Callable[..., Any]) -> Callable[[F], F]: ...


def keep_signature(original_func: Callable[..., Any]) -> Any:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        wrapped = wraps(original_func)(func)
        wrapped.__name__ = func.__name__
        wrapped.__qualname__ = func.__qualname__
        wrapped.__signature__ = signature(original_func)  # type: ignore[reportAttributeAccessIssue]
        return wrapped

    return decorator
