from typing import Any, Callable, TypeVar

from pydantic import BaseModel


class _Empty(BaseModel):
    pass


EMPTY = _Empty()
ReturnType = TypeVar("ReturnType")


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
