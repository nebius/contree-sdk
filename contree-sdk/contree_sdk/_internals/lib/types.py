from collections.abc import Callable
from dataclasses import dataclass
from typing import IO, Any, TypeVar

import cattrs
from aiofiles.threadpool.binary import AsyncBufferedReader


class _Empty:
    pass


EMPTY = _Empty()
ReturnType = TypeVar("ReturnType")


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


def to_dict(data: Any) -> Any:
    return cattrs.unstructure(data)


FileContent = IO[bytes] | bytes | str | AsyncBufferedReader
