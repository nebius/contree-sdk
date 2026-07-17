from asyncio import iscoroutinefunction, to_thread
from io import IOBase
from pathlib import Path
from subprocess import PIPE
from typing import cast

from contree_sdk._internals.io.operation_waiter import MAIN_SPID, OperationWaiter
from contree_sdk._internals.io.typing import (
    INPUT_TYPES,
    OUTPUT_REQUEST_TYPES,
    OUTPUT_TYPES,
    AsyncWritable,
    PipeIO,
    Writable,
)


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


async def connect_outputs(
    waiter: OperationWaiter,
    stdout_request: OUTPUT_REQUEST_TYPES | None,
    stderr_request: OUTPUT_REQUEST_TYPES | None,
    spid: int = MAIN_SPID,
):
    streams = {
        "stdout": get_output_obj(stdout_request),
        "stderr": get_output_obj(stderr_request),
    }
    for stream_name, output in streams.items():
        if output is None:
            continue
        await waiter.connect_output(
            output=output,
            spid=spid,
            stream_name=stream_name,
        )
    return streams["stdout"], streams["stderr"]


def get_output_obj(request: OUTPUT_REQUEST_TYPES | None) -> Writable | AsyncWritable | None:
    if request is None or request is str or request is bytes:
        return None
    if request is PIPE:
        return PipeIO()
    if isinstance(request, (str, Path)):
        return Path(request).open("wb")
    return cast(Writable | AsyncWritable, request)


def finalize_output(
    request: OUTPUT_REQUEST_TYPES | None,
    connected: Writable | AsyncWritable | None,
    buffer: bytes,
) -> OUTPUT_TYPES | Path | None:
    if request is None:
        return None
    if request is str:
        return buffer.decode()
    if request is bytes:
        return buffer
    if isinstance(connected, PipeIO):
        connected.close()
        return connected
    if isinstance(request, (str, Path)):
        if isinstance(connected, IOBase):
            connected.close()
        return Path(request)
    return connected
