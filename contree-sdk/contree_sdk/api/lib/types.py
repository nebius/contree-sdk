from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import TypeAdapter


class _Empty:
    pass


EMPTY = _Empty()
ReturnType = TypeVar("ReturnType")


class Body:
    pass


@dataclass(kw_only=True, frozen=True)
class ApiEndpointInfo:
    # api info
    method: str
    path: str

    # params info
    path_params: list[str]
    query_params: list[str]
    body_params: str | list[str]

    # how to parse
    json_path: list | None
    func: Callable[..., Any]
    return_type: ReturnType | _Empty

    def get_path_by_data(self, data: dict):
        return self.path.format(**data)

    def get_query_data_by_data(self, data: dict):
        return {name: to_json(data[name]) for name in self.query_params if name in data}

    def get_body_data_by_data(self, data: dict):
        if not self.body_params:
            return None
        res = {name: to_dict(data[name]) for name in self.body_params if name in data}
        if len(self.body_params) == 1:
            return res[self.body_params[0]]
        return res

    # todo for post


def to_json(data: Any) -> str:
    adapter = TypeAdapter(Any)
    return adapter.dump_json(data, exclude_none=True, by_alias=True).decode()


def to_dict(data: Any) -> Any:
    return TypeAdapter(Any).dump_python(data, by_alias=True, exclude_none=True)
