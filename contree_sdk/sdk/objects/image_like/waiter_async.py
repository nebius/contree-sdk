from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import suppress
from typing import TYPE_CHECKING, overload
from uuid import UUID

from contree_client.models import EventDataExit, EventDataTruncated, OperationStatus, decode_chunk

from contree_sdk.sdk.exceptions import CancelledOperationError, FailedOperationError, OperationTimedOutError
from contree_sdk.sdk.io.writer_wrapper import EOF, WriterToQueue, WriterWrapper
from contree_sdk.sdk.objects.image_like.waiter_common import (
    MAIN_SPID,
    STREAM_NAMES,
    OutputChunk,
    ProcessView,
    StreamName,
    synthetic_exit_event,
)
from contree_sdk.utils.sentinels import value_or_none


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from contree_client.base import ContreeAsyncClient
    from contree_client.models import OperationEvent, OperationResponse

    from contree_sdk.sdk.io.typing import AsyncWritable, Writable


class OperationWaiter:
    """Fans a single operation's event stream out to concurrent consumers.

    Built directly on `ContreeAsyncClient.follow_operation_events`, which
    already retries and reconnects on its own; this class only
    accumulates stdout/stderr per spid and lets `wait()` and
    `iter_output()` share one live subscription while running
    concurrently (`asyncio.Queue`-based fan-out, mirroring the old
    `connect_output`/`iter_chunks` shape).
    """

    def __init__(self, api: ContreeAsyncClient, operation_id: str, *, output_limit: int | None = None) -> None:
        self.api = api
        self.operation_id = operation_id
        self.outputs: dict[int, dict[str, bytearray]] = defaultdict(lambda: defaultdict(bytearray))
        self.readers: dict[tuple[int, str], list[WriterWrapper]] = defaultdict(list)
        self.exits: dict[int, EventDataExit] = {}
        self.truncated: dict[int, dict[str, EventDataTruncated]] = defaultdict(dict)
        # Caps how much of stdout/stderr we accumulate in `self.outputs`,
        # independent of the server's own `truncate_output_at` -- a safety
        # net against unbounded client-side memory growth if the caller
        # raises or disables that limit. Readers (e.g. a caller-supplied
        # file) still get the full, uncapped chunk.
        self.output_limit = output_limit
        self.finished = asyncio.Event()
        # True only once a `completion` event was actually observed -- as
        # opposed to `finished`, which also gets set when the load loop
        # stops on a timeout/error, so readers waiting on `connect_output`
        # still get finalized. `wait_for_result` uses this (not `finished`)
        # to decide whether the remote operation still needs cancelling.
        self.completed = False
        self.lock = asyncio.Lock()
        self.load_task: asyncio.Task[None] | None = None

    def ensure_loading(self, timeout: float | None) -> asyncio.Task[None]:
        if self.load_task is None:
            self.load_task = asyncio.create_task(self.load_events(timeout))
        return self.load_task

    async def load_events(self, timeout: float | None) -> None:
        try:
            async for event in self.api.follow_operation_events(self.operation_id, timeout=timeout):
                await self.process_event(event)
                if event.type == "completion":
                    self.completed = True
        finally:
            self.finished.set()
            async with self.lock:
                for readers in self.readers.values():
                    for reader in readers:
                        await reader.finalize()

    async def process_event(self, event: OperationEvent) -> None:
        spid = event.spid if isinstance(event.spid, int) else 0
        async with self.lock:
            if event.type in {"stdout", "stderr"}:
                chunk = decode_chunk(event.data)
                buffer = self.outputs[spid][event.type]
                if self.output_limit is not None:
                    retained = min(len(chunk), max(self.output_limit - len(buffer), 0))
                    buffer += chunk[:retained]
                else:
                    buffer += chunk
                for reader in self.readers[spid, event.type]:
                    await reader.write(chunk)
            elif isinstance(event.data, EventDataExit):
                self.exits[spid] = event.data
            elif isinstance(event.data, EventDataTruncated):
                self.truncated[spid][event.data.stream] = event.data

    async def connect_output(self, *, output: Writable | AsyncWritable, spid: int, stream_name: str) -> None:
        wrapper = WriterWrapper(output)
        async with self.lock:
            buffered = self.outputs[spid][stream_name]
            if buffered:
                await wrapper.write(bytes(buffered))
            if self.finished.is_set():
                await wrapper.finalize()
                return
            self.readers[spid, stream_name].append(wrapper)

    async def iter_chunks(self, spid: int) -> AsyncIterator[OutputChunk]:
        queues: dict[StreamName, asyncio.Queue] = {}
        for name in STREAM_NAMES:
            queue: asyncio.Queue = asyncio.Queue()
            queues[name] = queue
            await self.connect_output(output=WriterToQueue(queue=queue), spid=spid, stream_name=name)
        tasks = {asyncio.create_task(queue.get()): name for name, queue in queues.items()}
        try:
            while tasks:
                done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    name = tasks.pop(task)
                    value = task.result()
                    if value is EOF:
                        continue
                    yield OutputChunk(value=value, stream_name=name)
                    tasks[asyncio.create_task(queues[name].get())] = name
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def process_view(self, spid: int = MAIN_SPID) -> ProcessView:
        return ProcessView(
            exit=self.exits.get(spid),
            outputs={name: bytes(self.outputs[spid][name]) for name in STREAM_NAMES},
            truncated=dict(self.truncated[spid]),
        )

    async def cancel(self) -> None:
        # Best-effort cleanup, usually called from a `finally` while another
        # exception is already propagating -- suppress broadly so a cancel
        # failure never replaces/masks that original exception.
        with suppress(Exception):
            await self.api.cancel_operation(self.operation_id)

    @overload
    async def wait_for_result(
        self, *, timeout: float | None = None, spid: int = MAIN_SPID
    ) -> tuple[OperationResponse, EventDataExit]: ...
    @overload
    async def wait_for_result(self, *, timeout: float | None = None, spid: None) -> tuple[OperationResponse, None]: ...

    async def wait_for_result(
        self, *, timeout: float | None = None, spid: int | None = MAIN_SPID
    ) -> tuple[OperationResponse, EventDataExit | None]:
        task = self.ensure_loading(timeout)
        try:
            await task
        except (TimeoutError, asyncio.TimeoutError) as e:
            raise OperationTimedOutError(operation_uuid=UUID(self.operation_id)) from e
        finally:
            if not self.completed:
                await self.cancel()

        response = await self.api.get_operation_status(self.operation_id)
        if response.status == OperationStatus.CANCELLED:
            raise CancelledOperationError(operation_uuid=UUID(self.operation_id))
        if response.status == OperationStatus.FAILED:
            error = value_or_none(response.error) or "Unknown error"
            raise FailedOperationError(operation_uuid=UUID(self.operation_id), error=error)

        exit_event = self.exits.get(spid) if spid is not None else None
        if spid is not None and exit_event is None:
            # `self.exits` non-empty means other spids *did* report an exit --
            # this spid's is a genuine gap, not the fallback transport's
            # blanket "no exit events at all" case.
            if response.status != OperationStatus.SUCCESS or self.exits:
                raise FailedOperationError(
                    operation_uuid=UUID(self.operation_id),
                    error=f"no exit event received for spid {spid}",
                )
            # The transport's fallback mode (events endpoint unavailable)
            # only synthesizes a `completion` event -- the operation did
            # succeed, there's just no real exit detail to report.
            duration_ms = round((value_or_none(response.duration) or 0) * 1000)
            exit_event = synthetic_exit_event(pid=spid, duration_ms=duration_ms)
        if exit_event is not None and exit_event.timed_out:
            raise OperationTimedOutError(operation_uuid=UUID(self.operation_id))
        return response, exit_event
