from asyncio import iscoroutinefunction, to_thread
from pathlib import Path
from subprocess import PIPE

from contree_sdk._internals.utils.operation_waiter import MAIN_SPID, OperationWaiter
from contree_sdk.utils.io_wrap import INPUT_TYPES, OUTPUT_REQUEST_TYPES, OUTPUT_TYPES, PipeIO
from contree_sdk.utils.typing import AsyncWritable, Writable


async def read_input(request: INPUT_TYPES | None) -> str | bytes:
    if request is None:
        return ""
    if isinstance(request, (str, bytes)):
        return request
    if isinstance(request, Path):
        return await to_thread(request.read_bytes)
    read = request.read
    if iscoroutinefunction(read):
        return await read()
    return await to_thread(read)


async def connect_outputs(
    waiter: OperationWaiter,
    stdout_request: OUTPUT_REQUEST_TYPES,
    stderr_request: OUTPUT_REQUEST_TYPES,
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


def get_output_obj(request: OUTPUT_REQUEST_TYPES) -> Writable | AsyncWritable | None:
    if request is None or request is str or request is bytes:
        return None
    if request is PIPE:
        return PipeIO()
    if isinstance(request, (str, Path)):
        return Path(request).open("wb")
    return request


def finalize_output(
    request: OUTPUT_REQUEST_TYPES,
    connected: Writable | AsyncWritable | None,
    buffer: bytes,
) -> OUTPUT_TYPES | Path | None:
    if request is None:
        return None
    if request is str:
        return buffer.decode()
    if request is bytes:
        return buffer
    if request is PIPE:
        connected.close()
        return connected
    if isinstance(request, (str, Path)):
        connected.close()
        return Path(request)
    return connected
