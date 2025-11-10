import inspect
from functools import partial, wraps
from string import Formatter
from typing import TYPE_CHECKING, Annotated, Callable, Iterable, get_args, get_origin

from contree_sdk.client.helpers import args_kwargs_to_kwargs
from contree_sdk.client.types import EMPTY, ApiEndpointInfo, Body, ReturnType

if TYPE_CHECKING:
    from contree_sdk.client.client import ContreeClientBase

_formatter = Formatter()


# todo add proper typing
def apied(method, path, *, json: bool | Iterable[str] = False):
    match json:
        case False:
            json_path = None
        case True:
            json_path = []
        case _:
            json_path = json

    parsed_path_params = set()
    for (
        _,
        path_param,
        *_,
    ) in _formatter.parse(path):
        if path_param is None:
            continue
        parsed_path_params.add(path_param)

    def decorator(func: Callable[..., ReturnType]):
        path_params = []
        query_params = []
        body_params = []

        all_params = []

        sig = inspect.signature(func)
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            all_params.append(name)
            annotation = param.annotation
            # typ = annotation
            # default = param.default
            annotated_meta = None

            if get_origin(annotation) is Annotated:
                _, *meta = get_args(annotation)
                annotated_meta = meta or None

            if annotated_meta is Body:
                body_params.append(name)
            elif name in parsed_path_params:
                path_params.append(name)
            else:
                query_params.append(name)

        endpoint_info = ApiEndpointInfo(
            method=method,
            path=path,
            json_path=json_path,
            func=func,
            path_params=path_params,
            query_params=query_params,
            body_params=body_params,
            return_type=func.__annotations__.get("return", EMPTY),
        )

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            self: ContreeClientBase

            return self._handle_api_call(
                endpoint_info=endpoint_info, data=args_kwargs_to_kwargs(all_params, args, kwargs)
            )

        return wrapper

    return decorator


get = partial(apied, "get")
post = partial(apied, "post")
put = partial(apied, "put")
head = partial(apied, "head")
