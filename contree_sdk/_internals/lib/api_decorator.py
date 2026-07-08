from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import partial, wraps
from string import Formatter
from typing import TYPE_CHECKING

from contree_sdk._internals.lib.helpers import args_kwargs_to_kwargs
from contree_sdk._internals.lib.types import ApiEndpointInfo, ReturnType


if TYPE_CHECKING:
    from contree_sdk._internals.lib.client_base import ClientBase

_formatter = Formatter()


def apied(method: str, path: str, *, json: bool | Iterable[str] = False):
    """Define an API endpoint on a client method.

    Builds ApiEndpointInfo from the function signature and annotations, then
    replaces the method with a wrapper calling `_handle_api_call`.

    Args:
        method: HTTP method name.
        path: Endpoint path with `{param}` placeholders.
        json:
            False — no JSON handling,
            True — whole response as JSON,
            iterable — JSON path to extract.

    Returns:
        A decorator that wraps a client method and routes the call through
        `ClientBase._handle_api_call`.

    """
    match json:
        case False:
            json_path = None
        case True:
            json_path = []
        case _:
            json_path = list(json)

    def decorator(func: Callable[..., ReturnType]):
        endpoint_info = ApiEndpointInfo.from_func(
            method=method,
            path=path,
            json_path=json_path,
            func=func,
        )

        @wraps(func)
        async def wrapper(self: ClientBase, *args, **kwargs):
            data = args_kwargs_to_kwargs(endpoint_info.all_params, args, kwargs)
            return await self._handle_api_call(endpoint_info=endpoint_info, data=data)

        return wrapper

    return decorator


get = partial(apied, "get")
post = partial(apied, "post")
patch = partial(apied, "patch")
put = partial(apied, "put")
head = partial(apied, "head")
delete = partial(apied, "delete")
