from typing import Any, Callable, TypeVar

from pydantic import BaseModel, TypeAdapter


class _Empty(BaseModel):
    pass


EMPTY = _Empty()
ReturnType = TypeVar("ReturnType")


class Body:
    pass


class ApiEndpointInfo(BaseModel):
    # api info
    method: str
    path: str

    # params info
    path_params: list[str] = []
    query_params: list[str] = []
    body_params: str | list[str] = []

    # how to parse
    json_path: list | None
    func: Callable[..., Any]
    return_type: ReturnType | _Empty

    def get_path_by_data(self, data: dict):
        return self.path.format(**data)

    def get_query_data_by_data(self, data: dict):
        return {name: to_json(data[name]) for name in self.query_params if name in data}

    # todo for post


def to_json(data: Any) -> str:
    adapter = TypeAdapter(Any)
    return adapter.dump_json(data, exclude_none=True, by_alias=True).decode()


def to_dict(data: Any) -> Any:
    return TypeAdapter(Any).dump_python(data, by_alias=True, exclude_none=True)
