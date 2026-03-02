import asyncio
import sys
import warnings
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar


__all__ = ["deprecated"]

P = ParamSpec("P")
T = TypeVar("T")

if sys.version_info >= (3, 13):
    from warnings import deprecated
else:
    from typing_extensions import deprecated as _typing_deprecated

    def deprecated(
        message: str,
        *,
        category: type[Warning] = DeprecationWarning,
        stacklevel: int = 1,
    ) -> Callable[[Callable[P, T]], Callable[P, T]]:
        """Mark a function or method as deprecated.

        Provides both runtime warnings and type checker / IDE support.

        Returns:
            Decorator that marks the function as deprecated.

        Example:
            @deprecated("Use new_method instead")
            async def old_method(): ...

        """

        def decorator(func: Callable[P, T]) -> Callable[P, T]:
            typed_func: Callable[P, T] = _typing_deprecated(message)(func)  # type: ignore[arg-type]
            warn_msg = f"{func.__qualname__} is deprecated. {message}"

            if asyncio.iscoroutinefunction(func):

                @wraps(typed_func)
                async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                    warnings.warn(warn_msg, category=category, stacklevel=stacklevel + 1)
                    return await func(*args, **kwargs)

                return async_wrapper  # type: ignore[return-value]

            @wraps(typed_func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                warnings.warn(warn_msg, category=category, stacklevel=stacklevel + 1)
                return func(*args, **kwargs)

            return sync_wrapper

        return decorator
