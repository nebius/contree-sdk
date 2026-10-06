"""A spawned operation's lifecycle control, decoupled from ContreeAsyncSession.run() (async).

Mirrors `contree_sdk.session.operation_sync` with a real `asyncio.Task` in place
of a background thread, and `asyncio.Queue` in place of `queue.Queue` - not one
bridged from the other, per the project's Sync/Async pairing convention.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterable, AsyncIterator, Iterable
from contextlib import suppress
from typing import IO

from contree_client.models import InstanceResult, OperationEvent, OperationResponse
from contree_client.types import ContreeAsyncClient

from contree_sdk.compat import Self
from contree_sdk.execution import OperationContext
from contree_sdk.session.base import encode_stdin_chunk, instance_result, stream_repr_for_stdin, write_stream_chunk
from contree_sdk.session.contracts import AsyncOperationContract, AsyncOperationObserver, AsyncSubprocessContract
from contree_sdk.session.stdin import DEFAULT_STDIN_CHUNK_SIZE, StdinResult, stdin_chunks


DEFAULT_SHUTDOWN_SIGNAL = "SIGTERM"


class AsyncOperation(AsyncOperationContract):
    """Handle to a spawned instance operation, identified by its UUID."""

    def __init__(
        self,
        client: ContreeAsyncClient,
        operation_uuid: str,
        *,
        timeout: float | None = None,
        shutdown_timeout: float = 10.0,
        files: tuple[str, ...] = (),
        context: OperationContext | None = None,
    ) -> None:
        self.client = client
        self.uuid = operation_uuid
        self.timeout = timeout
        self.shutdown_timeout = shutdown_timeout
        # destination paths already uploaded for this spawn (set by ContreeAsyncSession.spawn(),
        # so commit_result() can record them without uploading the same content again)
        self.context = context
        self.files = context.files if context is not None else files
        self.response: OperationResponse | None = None
        self.queues: dict[int, asyncio.Queue[OperationEvent | None]] = {}
        # events for a spid `run()` hasn't registered a queue for yet - the pump
        # task can race ahead of run() and observe a spid's events (including its
        # own exit) before the caller gets a chance to claim them; buffering here and
        # flushing on registration (see claim_queue()) closes that race
        self.pending_events: dict[int, asyncio.Queue[OperationEvent]] = {}
        self.terminal = False
        self.stream_error: Exception | None = None
        self.observers: list[AsyncOperationObserver] = []
        self.terminal_event = asyncio.Event()
        self.consumer_task: asyncio.Task[None] | None = None
        self.lock = asyncio.Lock()
        self.history: list[OperationEvent] = []
        self.spawned: set[int] = set()
        self.exited: set[int] = set()
        self.completion_received = False
        self.entered = False
        self.changed = asyncio.Condition()
        self.result_lock = asyncio.Lock()
        self.final_response: OperationResponse | None = None

    def add_observer(self, observer: AsyncOperationObserver) -> None:
        if self.consumer_task is not None:
            raise RuntimeError("register observers before starting the event reader")
        self.observers.append(observer)

    def open_event_stream(self) -> AsyncIterator[OperationEvent]:
        """Open the unfiltered source. Override this hook to supply custom events.

        Returns:
            The single transport stream consumed by the operation.

        """
        return self.client.follow_operation_events(self.uuid)

    async def _start_reader(self) -> None:
        async with self.lock:
            if self.consumer_task is None:
                self.consumer_task = asyncio.create_task(self.pump())

    async def events(
        self, *, since: int | None = None, spid: int | None = None, timeout: float | None = None
    ) -> AsyncIterator[OperationEvent]:
        """Replay buffered events, then follow the shared reader with local filters.

        timeout bounds this subscription. Expiry does not cancel the operation.

        Yields:
            Events after ``since`` whose process matches ``spid``, when specified.

        Raises:
            TimeoutError: The subscription did not finish before timeout.

        """
        await self._start_reader()
        deadline = None if timeout is None else time.monotonic() + timeout
        cursor = 0
        while True:
            async with self.changed:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    raise TimeoutError(f"operation {self.uuid} events did not complete in time")
                await asyncio.wait_for(
                    self.changed.wait_for(
                        lambda cursor=cursor: cursor < len(self.history) or self.terminal_event.is_set()
                    ),
                    timeout=remaining,
                )
                if cursor == len(self.history):
                    if self.stream_error is not None:
                        raise self.stream_error
                    return
                event = self.history[cursor]
                cursor += 1
            if (since is None or event.id > since) and (spid is None or event.spid == spid):
                yield event

    async def status(self, *, inflight: bool = False) -> OperationResponse:
        self.response = await self.client.get_operation_status(self.uuid, inflight=inflight)
        return self.response

    async def send_stdin(self, data: str | bytes, *, spid: int = 1, close: bool = True) -> None:
        value, encoding = encode_stdin_chunk(data)
        await self.client.operation_subprocess_stdin(self.uuid, spid, value, encoding=encoding, close=close)

    def _process_ended(self, spid: int) -> bool:
        if self.stream_error is not None:
            raise self.stream_error
        return spid in self.exited or self.completion_received or self.terminal_event.is_set()

    async def pipe_stdin(
        self,
        chunks: AsyncIterable[str | bytes],
        *,
        spid: int = 1,
        close: bool = True,
        chunk_size: int = DEFAULT_STDIN_CHUNK_SIZE,
    ) -> StdinResult:
        """Forward chunks after spawn and stop waiting for input when the process exits.

        Use one writer per process. Errors and cancellation stop the target process; spid=1 cancels the operation.
        A pending source read is cancelled on exit; the caller owns the source.

        Returns:
            Acknowledged bytes, EOF delivery, and observed early completion.

        Raises:
            ValueError: chunk_size or spid is not positive.

        """
        if chunk_size <= 0 or spid < 1:
            raise ValueError("chunk_size and spid must be positive")
        try:
            return await self._pipe_stdin(aiter(chunks), spid, close=close, chunk_size=chunk_size)
        except BaseException:
            with suppress(Exception):
                await asyncio.shield(self.cancel() if spid == 1 else self.signal("SIGKILL", spid=spid))
            raise

    async def _wait_process_exit(self, spid: int) -> None:
        async with self.changed:
            await self.changed.wait_for(lambda: self._process_ended(spid))

    @staticmethod
    async def _next_stdin(chunks: AsyncIterator[str | bytes], ended: asyncio.Task[None]) -> str | bytes:
        read = asyncio.ensure_future(anext(chunks))
        try:
            done, _ = await asyncio.wait((read, ended), return_when=asyncio.FIRST_COMPLETED)
            if ended in done:
                ended.result()
                return b""
            return read.result()
        finally:
            read.cancel()
            # Retrieve errors if exit and input became ready in the same loop iteration.
            await asyncio.gather(read, return_exceptions=True)

    async def _pipe_stdin(
        self, chunks: AsyncIterator[str | bytes], spid: int, *, close: bool, chunk_size: int
    ) -> StdinResult:
        await self._start_reader()
        async with self.changed:
            await self.changed.wait_for(lambda: spid in self.spawned or self._process_ended(spid))
        ended = asyncio.create_task(self._wait_process_exit(spid))
        sent = 0
        try:
            while not self._process_ended(spid):
                try:
                    data = await self._next_stdin(chunks, ended)
                except StopAsyncIteration:
                    break
                for part in stdin_chunks(data, chunk_size):
                    if self._process_ended(spid):
                        return StdinResult(sent, process_exited=True)
                    await self.send_stdin(part, spid=spid, close=False)
                    sent += len(part)
            if self._process_ended(spid):
                return StdinResult(sent, process_exited=True)
            if close:
                await self.send_stdin(b"", spid=spid, close=True)
            return StdinResult(sent, eof_sent=close)
        finally:
            ended.cancel()
            await asyncio.gather(ended, return_exceptions=True)

    async def signal(self, sig: str | None = None, *, spid: int = 1) -> None:
        await self.client.operation_subprocess_kill(self.uuid, spid, signal=sig)

    async def cancel(self) -> None:
        await self.client.cancel_operation(self.uuid)

    async def wait(self, *, timeout: float | None = None) -> InstanceResult:
        try:
            await self._start_reader()
            await asyncio.wait_for(self.terminal_event.wait(), timeout=self.timeout if timeout is None else timeout)
            return await self._completed_result()
        except BaseException:
            with suppress(Exception):
                await asyncio.shield(self.cancel())
            raise

    async def _completed_result(self) -> InstanceResult:
        if self.stream_error is not None:
            raise self.stream_error
        async with self.result_lock:
            if self.final_response is None:
                self.final_response = await self.status()
            return instance_result(self.final_response)

    async def __aenter__(self) -> Self:
        self.entered = True
        await self._start_reader()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            await self.shutdown()
        else:
            with suppress(Exception):
                await asyncio.shield(self.shutdown())

    def _remember_event(self, event: OperationEvent) -> None:
        self.history.append(event)
        if event.type == "spawn" and isinstance(event.spid, int):
            self.spawned.add(event.spid)
        elif event.type == "exit" and isinstance(event.spid, int):
            self.exited.add(event.spid)
        elif event.type == "completion":
            self.completion_received = True

    async def pump(self) -> None:
        # single background reader for the whole operation's event stream (unfiltered:
        # a server-side spid filter would also drop the operation-wide `completion`
        # event, since `completion` carries no spid at all), demultiplexed by spid
        # into whichever queue `run()` registered for that spid - or buffered in
        # pending_events if run() hasn't registered one yet (see __init__)
        source: AsyncIterator[OperationEvent] | None = None
        try:  # noqa: PLW0717 - one event stream must have one error and cleanup boundary
            source = self.open_event_stream()
            async for event in source:
                for observer in self.observers:
                    await observer(event, None)
                async with self.changed:
                    self._remember_event(event)
                    self.changed.notify_all()
                if event.type == "completion":
                    break
                spid = event.spid
                if not isinstance(spid, int) or spid == 1:
                    continue
                async with self.lock:
                    target = self.queues.get(spid)
                    if target is None:
                        buffer = self.pending_events.setdefault(spid, asyncio.Queue())
                        await buffer.put(event)
                        continue
                await target.put(event)
        except asyncio.CancelledError:
            self.stream_error = RuntimeError("operation event reader was cancelled")
            raise
        except Exception as error:
            self.stream_error = error
        finally:
            await self._close_event_stream(source)
            for observer in self.observers:
                try:
                    await observer(None, self.stream_error)
                except Exception as error:  # noqa: PERF203 - notify remaining observers after an error
                    if self.stream_error is None:
                        self.stream_error = error
            async with self.lock:
                self.terminal = True
                for target in self.queues.values():
                    target.put_nowait(None)
            async with self.changed:
                self.terminal_event.set()
                self.changed.notify_all()

    async def _close_event_stream(self, source: AsyncIterator[OperationEvent] | None) -> None:
        close = getattr(source, "aclose", None)
        if close is not None:
            try:
                await close()
            except Exception as error:
                if self.stream_error is None:
                    self.stream_error = error

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
        uid: int | None = None,
        gid: int | None = None,
        stdin: str | bytes | None = None,
        stdin_open: bool = False,
        truncate_output_at: int | None = None,
    ) -> AsyncSubprocessContract:
        if not self.entered:
            raise RuntimeError(
                "AsyncOperation.run() requires the operation to be used as a context manager ('async with')"
            )
        stdin_repr = (
            stream_repr_for_stdin(stdin or b"", close=not stdin_open) if stdin is not None or stdin_open else ...
        )
        spid = await self.client.operation_subprocess_create(
            self.uuid,
            command,
            args=list(args) if args else ...,
            shell=shell,
            env=env if env is not None else ...,
            cwd=cwd if cwd is not None else ...,
            uid=uid if uid is not None else ...,
            gid=gid if gid is not None else ...,
            stdin=stdin_repr,
            truncate_output_at=truncate_output_at if truncate_output_at is not None else ...,
        )
        return self.create_subprocess(spid, await self.claim_queue(spid))

    def create_subprocess(
        self, spid: int, events_queue: asyncio.Queue[OperationEvent | None]
    ) -> AsyncSubprocessContract:
        """Create a subprocess handle. Override to return a custom implementation.

        Returns:
            A handle consuming the supplied event queue.

        """
        return AsyncSubprocessHandle(self, spid, events_queue)

    async def shutdown(self) -> None:
        try:
            if self.stream_error is not None:
                await self.cancel()
            elif not self.terminal:
                try:
                    await self.signal(DEFAULT_SHUTDOWN_SIGNAL)
                    with suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(self.terminal_event.wait(), timeout=self.shutdown_timeout)
                finally:
                    if not self.terminal:
                        await self.cancel()
        finally:
            if self.consumer_task is not None:
                try:
                    await asyncio.wait_for(self.consumer_task, timeout=self.shutdown_timeout)
                except asyncio.TimeoutError:
                    self.consumer_task.cancel()
                finally:
                    if not self.consumer_task.done():
                        self.consumer_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await self.consumer_task
        if self.stream_error is not None:
            raise self.stream_error


class AsyncSubprocessHandle(AsyncSubprocessContract):
    """Both awaitable (final result) and async-iterable (live events) for one spid."""

    def __init__(
        self, operation: AsyncOperation, spid: int, events_queue: asyncio.Queue[OperationEvent | None]
    ) -> None:
        self.operation = operation
        self.spid = spid
        self.queue = events_queue
        self.finished = False
        self.result: InstanceResult | None = None

    async def iterate(self) -> AsyncIterator[OperationEvent]:
        while not self.finished:
            item = await self.queue.get()
            if item is None:
                self.finished = True
                if self.operation.stream_error is not None:
                    raise self.operation.stream_error
                return
            if item.type == "exit":
                self.finished = True
            yield item

    def __aiter__(self) -> AsyncIterator[OperationEvent]:
        return self.iterate()

    def __await__(self):
        return self.wait().__await__()

    async def wait(self, *, timeout: float | None = None) -> InstanceResult:
        deadline = None if timeout is None else time.monotonic() + timeout
        while not self.finished:
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
                self.finished = True
                if item is None and self.operation.stream_error is not None:
                    raise self.operation.stream_error
        if self.result is None:
            self.result = await self.operation.client.operation_subprocess(self.operation.uuid, self.spid)
        return self.result

    async def pipe_to(
        self, *, stdout: IO[str] | IO[bytes] | None = None, stderr: IO[str] | IO[bytes] | None = None
    ) -> InstanceResult:
        async for event in self:
            if event.type == "stdout" and stdout is not None:
                write_stream_chunk(stdout, event.data)
            elif event.type == "stderr" and stderr is not None:
                write_stream_chunk(stderr, event.data)
        if self.result is None:
            self.result = await self.operation.client.operation_subprocess(self.operation.uuid, self.spid)
        return self.result
