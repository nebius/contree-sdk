from __future__ import annotations

from asyncio import iscoroutinefunction, to_thread
from dataclasses import dataclass
from io import IOBase
from pathlib import Path
from subprocess import PIPE
from typing import TYPE_CHECKING, NamedTuple, cast

from contree_sdk._internals.io.operation_waiter import MAIN_SPID, OperationWaiter, ProcessView
from contree_sdk._internals.io.typing import (
    INPUT_TYPES,
    OUTPUT_REQUEST_TYPES,
    OUTPUT_TYPES,
    AsyncWritable,
    PipeIO,
    Writable,
)


if TYPE_CHECKING:
    from contree_sdk.sdk.objects.run import RunRequest


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


class FinalizedOutputs(NamedTuple):
    stdout: OUTPUT_TYPES | Path | None
    stderr: OUTPUT_TYPES | Path | None


@dataclass
class OperationOutputs:
    stdout_request: OUTPUT_REQUEST_TYPES | None
    stderr_request: OUTPUT_REQUEST_TYPES | None
    stdout: Writable | AsyncWritable | None
    stderr: Writable | AsyncWritable | None

    @classmethod
    def from_request(cls, request: RunRequest) -> OperationOutputs:
        return cls(
            stdout_request=request.stdout,
            stderr_request=request.stderr,
            stdout=get_output_obj(request.stdout),
            stderr=get_output_obj(request.stderr),
        )

    async def connect(self, waiter: OperationWaiter, spid: int = MAIN_SPID) -> None:
        for stream_name, output in (("stdout", self.stdout), ("stderr", self.stderr)):
            if output is None:
                continue
            await waiter.connect_output(output=output, spid=spid, stream_name=stream_name)

    def finalize(self, view: ProcessView) -> FinalizedOutputs:
        return FinalizedOutputs(
            stdout=finalize_output(self.stdout_request, self.stdout, view.outputs["stdout"]),
            stderr=finalize_output(self.stderr_request, self.stderr, view.outputs["stderr"]),
        )

    def close(self) -> None:
        for request, connected in ((self.stdout_request, self.stdout), (self.stderr_request, self.stderr)):
            if isinstance(request, (str, Path)) and isinstance(connected, IOBase):
                connected.close()


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
