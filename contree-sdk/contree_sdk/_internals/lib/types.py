from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from string import Formatter
from typing import IO, Annotated, Any, TypeVar, get_args, get_origin

import cattrs
from aiofiles.threadpool.binary import AsyncBufferedReader


class _Empty:
    pass


EMPTY = _Empty()
ReturnType = TypeVar("ReturnType")
_formatter = Formatter()


class Body:
    pass


class OctetFile:
    pass


@dataclass(kw_only=True, frozen=True)
class ApiEndpointInfo:
    # api info
    method: str
    path: str

    # params info
    all_params: list[str]
    path_params: list[str]
    query_params: list[str]
    body_params: list[str]
    file_params: list[str]

    # how to parse
    json_path: list | None
    func: Callable[..., Any]
    return_type: ReturnType | _Empty

    def get_path_by_data(self, data: dict):
        return self.path.format(**data)

    def get_query_data_by_data(self, data: dict):
        return {name: str(to_dict(data[name])) for name in self.query_params if name in data}

    def get_body_data_by_data(self, data: dict):
        if not self.body_params:
            return None
        res = {name: to_dict(data[name]) for name in self.body_params if name in data}
        if len(self.body_params) == 1:
            return res[self.body_params[0]]
        return res

    def get_file_upload_kwargs(self, data: dict) -> dict:
        if not self.file_params:
            return {}
        if len(self.file_params) == 1:
            return {
                "headers": {
                    "Content-Type": "application/octet-stream",
                },
                "content": data[self.file_params[0]],
            }
        return {"files": {name: (None, data[name], "application/octet-stream") for name in self.file_params}}

    @classmethod
    def from_func(
        cls,
        *,
        method: str,
        path: str,
        json_path: list | None,
        func: Callable[..., Any],
    ) -> ApiEndpointInfo:
        parsed_path_params = {name for _, name, *_ in _formatter.parse(path) if name is not None}

        all_params: list[str] = []
        path_params: list[str] = []
        query_params: list[str] = []
        body_params: list[str] = []
        file_params: list[str] = []

        sig = inspect.signature(func)
        for name, param in sig.parameters.items():
            if name == "self":
                continue
            all_params.append(name)

            is_body, is_file = cls._extract_flags(param)

            if is_body:
                body_params.append(name)
            elif is_file:
                file_params.append(name)
            elif name in parsed_path_params:
                path_params.append(name)
            else:
                query_params.append(name)

        return cls(
            method=method,
            path=path,
            all_params=all_params,
            path_params=path_params,
            query_params=query_params,
            body_params=body_params,
            file_params=file_params,
            json_path=json_path,
            func=func,
            return_type=func.__annotations__.get("return", EMPTY),
        )

    @staticmethod
    def _extract_flags(param: inspect.Parameter) -> tuple[bool, bool]:
        ann = param.annotation
        if get_origin(ann) is not Annotated:
            return False, False

        _, *meta = get_args(ann)

        is_body = any(isinstance(m, type) and issubclass(m, Body) for m in meta)
        is_file = any(isinstance(m, type) and issubclass(m, OctetFile) for m in meta)
        return is_body, is_file


def to_dict(data: Any) -> Any:
    return cattrs.unstructure(data)


FileContent = IO[bytes] | bytes | str | AsyncBufferedReader
