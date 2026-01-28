from collections.abc import Callable
from functools import wraps
from typing import TypeVar


F = TypeVar("F", bound=Callable)


def keep_signature(original_func: Callable) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        wrapped = wraps(original_func)(func)
        wrapped.__name__ = func.__name__
        wrapped.__qualname__ = func.__qualname__
        return wrapped

    return decorator
