"""A spawned operation's lifecycle control, decoupled from ContreeAsyncSession.run() (async).

Mirrors `contree_sdk.session.operation_sync` with a real `asyncio.Task` in place
of a background thread, and `asyncio.Queue` in place of `queue.Queue` - not one
bridged from the other, per the project's Sync/Async pairing convention.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import time
from collections.abc import AsyncIterator, Iterable
from contextlib import suppress
from io import TextIOBase
from typing import IO, TYPE_CHECKING, Any, Literal

from typing_extensions import Self

from contree_sdk.session.base import instance_result, stream_repr_for_stdin


if TYPE_CHECKING:
    from contree_client.models import InstanceResult, OperationEvent, OperationResponse
    from contree_client.types import ContreeAsyncClient


DEFAULT_SHUTDOWN_SIGNAL = "SIGTERM"


def encode_stdin_chunk(data: str | bytes) -> tuple[str, Literal["ascii", "base64"]]:
    if isinstance(data, bytes):
        return base64.b64encode(data).decode("ascii"), "base64"
    return data, "ascii"


def decode_stream_value(value: str, encoding: str) -> bytes:
    if not value:
        return b""
    if encoding == "base64":
        try:
            return base64.b64decode(value)
        except (binascii.Error, ValueError):
            return b""
    return value.encode("utf-8", errors="replace")


def write_stream_chunk(stream: IO[str] | IO[bytes], data: Any) -> None:
    raw = decode_stream_value(data.value, data.encoding)
    if isinstance(stream, TextIOBase):
        stream.write(raw.decode("utf-8", errors="replace"))  # ty: ignore[no-matching-overload]
    else:
        stream.write(raw)  # ty: ignore[no-matching-overload]


class AsyncOperation:
    """Handle to a spawned instance operation, identified by its UUID."""

    def __init__(
        self,
        client: ContreeAsyncClient,
        operation_uuid: str,
        *,
        timeout: float | None = None,
        shutdown_timeout: float = 10.0,
        files: tuple[str, ...] = (),
    ) -> None:
        self.client = client
        self.uuid = operation_uuid
        self.timeout = timeout
        self.shutdown_timeout = shutdown_timeout
        # destination paths already uploaded for this spawn (set by ContreeAsyncSession.spawn(),
        # so commit_result() can record them without uploading the same content again)
        self.files = files
        self.response: OperationResponse | None = None
        self.queues: dict[int, asyncio.Queue[OperationEvent | None]] = {}
        # events for a spid `run()` hasn't registered a queue for yet - the pump
        # task can race ahead of run() and observe a spid's events (including its
        # own exit) before the caller gets a chance to claim them; buffering here and
        # flushing on registration (see claim_queue()) closes that race
        self.pending_events: dict[int, asyncio.Queue[OperationEvent]] = {}
        self.terminal = False
        self.terminal_event = asyncio.Event()
        self.consumer_task: asyncio.Task[None] | None = None
        self.lock = asyncio.Lock()

    def events(self, *, since: int | None = None, spid: int | None = None) -> AsyncIterator[OperationEvent]:
        return self.client.follow_operation_events(self.uuid, since=since, spid=spid)

    async def status(self, *, inflight: bool = False) -> OperationResponse:
        self.response = await self.client.get_operation_status(self.uuid, inflight=inflight)
        return self.response

    async def send_stdin(self, data: str | bytes, *, spid: int = 1, close: bool = True) -> None:
        value, encoding = encode_stdin_chunk(data)
        await self.client.operation_subprocess_stdin(self.uuid, spid, value, encoding=encoding, close=close)

    async def signal(self, sig: str | None = None, *, spid: int = 1) -> None:
        await self.client.operation_subprocess_kill(self.uuid, spid, signal=sig)

    async def cancel(self) -> None:
        await self.client.cancel_operation(self.uuid)

    async def wait(self, *, timeout: float | None = None) -> InstanceResult:
        self.response = await self.client.wait_operation(
            self.uuid, timeout=timeout if timeout is not None else self.timeout
        )
        return instance_result(self.response)

    async def __aenter__(self) -> Self:
        async with self.lock:
            if self.consumer_task is None:
                self.consumer_task = asyncio.ensure_future(self.pump())
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.shutdown()

    async def pump(self) -> None:
        # single background reader for the whole operation's event stream (unfiltered:
        # a server-side spid filter would also drop the operation-wide `completion`
        # event, since `completion` carries no spid at all), demultiplexed by spid
        # into whichever queue `run()` registered for that spid - or buffered in
        # pending_events if run() hasn't registered one yet (see __init__)
        try:
            async for event in self.client.follow_operation_events(self.uuid):
                if event.type == "completion":
                    break
                spid = event.spid
                if not isinstance(spid, int):
                    continue
                async with self.lock:
                    target = self.queues.get(spid)
                    if target is None:
                        buffer = self.pending_events.setdefault(spid, asyncio.Queue())
                        await buffer.put(event)
                        continue
                await target.put(event)
        finally:
            async with self.lock:
                self.terminal = True
                queues = list(self.queues.values())
            self.terminal_event.set()
            for target in queues:
                await target.put(None)

    async def claim_queue(self, spid: int) -> asyncio.Queue[OperationEvent | None]:
        # registers spid's queue, flushing anything pump() buffered for it before this
        # call could run; if the operation already ended, closes the handle immediately
        # so a subprocess whose exit raced ahead of this registration doesn't hang forever
        subprocess_queue: asyncio.Queue[OperationEvent | None] = asyncio.Queue()
        async with self.lock:
            buffered = self.pending_events.pop(spid, None)
            if buffered is not None:
                while not buffered.empty():
                    subprocess_queue.put_nowait(buffered.get_nowait())
            if self.terminal:
                subprocess_queue.put_nowait(None)
            else:
                self.queues[spid] = subprocess_queue
        return subprocess_queue

    async def run(
        self,
        command: str,
        *,
        shell: bool = False,
        args: Iterable[str] = (),
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        stdin: str | bytes | None = None,
        truncate_output_at: int | None = None,
    ) -> AsyncSubprocessHandle:
        if self.consumer_task is None:
            raise RuntimeError(
                "AsyncOperation.run() requires the operation to be used as a context manager ('async with')"
            )
        stdin_repr = stream_repr_for_stdin(stdin) if stdin is not None else ...
        spid = await self.client.operation_subprocess_create(
            self.uuid,
            command,
            args=list(args) if args else ...,
            shell=shell,
            env=env if env is not None else ...,
            cwd=cwd if cwd is not None else ...,
            stdin=stdin_repr,
            truncate_output_at=truncate_output_at if truncate_output_at is not None else ...,
        )
        return AsyncSubprocessHandle(self, spid, await self.claim_queue(spid))

    async def shutdown(self) -> None:
        # graceful-then-forceful: signal spid=1, give it shutdown_timeout to reach a
        # terminal status (observed via the consumer task's terminal_event), else force-cancel
        if not self.terminal:
            await self.signal(DEFAULT_SHUTDOWN_SIGNAL)
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.terminal_event.wait(), timeout=self.shutdown_timeout)
            if not self.terminal:
                await self.cancel()
        if self.consumer_task is not None:
            try:
                await asyncio.wait_for(self.consumer_task, timeout=self.shutdown_timeout)
            except asyncio.TimeoutError:
                self.consumer_task.cancel()


class AsyncSubprocessHandle:
    """Both awaitable (final result) and async-iterable (live events) for one spid."""

    def __init__(
        self, operation: AsyncOperation, spid: int, events_queue: asyncio.Queue[OperationEvent | None]
    ) -> None:
        self.operation = operation
        self.spid = spid
        self.queue = events_queue

    async def iterate(self) -> AsyncIterator[OperationEvent]:
        while True:
            item = await self.queue.get()
            if item is None:
                return
            yield item
            if item.type == "exit":
                return

    def __aiter__(self) -> AsyncIterator[OperationEvent]:
        return self.iterate()

    def __await__(self):
        return self.wait().__await__()

    async def wait(self, *, timeout: float | None = None) -> InstanceResult:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            remaining: float | None = None
            if deadline is not None:
                remaining = max(0.0, deadline - time.monotonic())
                if remaining <= 0:
                    raise TimeoutError(f"subprocess spid={self.spid} did not exit within {timeout}s")
            try:
                item = await (self.queue.get() if remaining is None else asyncio.wait_for(self.queue.get(), remaining))
            except asyncio.TimeoutError:
                raise TimeoutError(f"subprocess spid={self.spid} did not exit within {timeout}s") from None
            if item is None or item.type == "exit":
                break
        return await self.operation.client.operation_subprocess(self.operation.uuid, self.spid)

    async def pipe_to(
        self, *, stdout: IO[str] | IO[bytes] | None = None, stderr: IO[str] | IO[bytes] | None = None
    ) -> InstanceResult:
        async for event in self:
            if event.type == "stdout" and stdout is not None:
                write_stream_chunk(stdout, event.data)
            elif event.type == "stderr" and stderr is not None:
                write_stream_chunk(stderr, event.data)
        return await self.operation.client.operation_subprocess(self.operation.uuid, self.spid)
