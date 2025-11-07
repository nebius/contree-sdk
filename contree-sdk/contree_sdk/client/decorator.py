from functools import partial, wraps
from typing import TYPE_CHECKING, Callable, Iterable

from contree_sdk.client.types import EMPTY, ApiEndpointInfo, ReturnType

if TYPE_CHECKING:
    from contree_sdk.client.base import ContreeClientBase


# todo add proper typing
def apied(method, path, *, json: bool | Iterable[str] = False):
    match json:
        case False:
            json_path = None
        case True:
            json_path = []
        case _:
            json_path = json

    def decorator(func: Callable[..., ReturnType]):
        endpoint_info = ApiEndpointInfo(
            method=method,
            path=path,
            json_path=json_path,
            func=func,
            return_type=func.__annotations__.get("return", EMPTY),
        )

        @wraps(func)
        def wrapper(self, **kwargs):
            self: ContreeClientBase

            return self._handle_api_call(endpoint_info=endpoint_info, data=kwargs)

        return wrapper

    return decorator


get = partial(apied, "get")
post = partial(apied, "post")
put = partial(apied, "put")
head = partial(apied, "head")
