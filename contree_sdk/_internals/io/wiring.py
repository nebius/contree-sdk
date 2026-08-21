from __future__ import annotations

from asyncio import iscoroutinefunction, to_thread
from pathlib import Path
from typing import cast

from contree_sdk._internals.io.typing import INPUT_TYPES


async def read_input(request: INPUT_TYPES | None) -> str | bytes:
    if request is None:
        return ""
    if isinstance(request, (str, bytes)):
        return request
    if isinstance(request, Path):
        return await to_thread(request.read_bytes)
    read = request.read
    if iscoroutinefunction(read):
        data = await read()
    else:
        data = await to_thread(read)
    return cast("str | bytes", data)


def read_input_sync(request: INPUT_TYPES | None) -> str | bytes:
    if request is None:
        return ""
    if isinstance(request, (str, bytes)):
        return request
    if isinstance(request, Path):
        return request.read_bytes()
    read = request.read
    if iscoroutinefunction(read):
        raise TypeError("an async-readable stdin source requires the async ContreeAsyncSession")
    return cast("str | bytes", read())
