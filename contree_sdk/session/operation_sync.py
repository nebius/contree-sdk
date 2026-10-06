"""A spawned operation's lifecycle control, decoupled from ContreeSession.run() (sync).

`Operation` works in two modes. Simple mode (`events`/`status`/`send_stdin`/
`signal`/`cancel`/`wait`) is a set of thin, stateless forwards to the client,
keyed by the operation's UUID. Rich mode, entered via `with operation:`,
starts a background thread that continuously consumes the operation's event
stream and demultiplexes it by spid, unlocking `run()` - spawning an
*additional* process inside the same running instance (`spid` >= 2, via
`operation_subprocess_create`) and getting back a `SubprocessHandle` that is
both blocking-waitable (the subprocess's own final result) and iterable (its
live events).
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Iterable, Iterator
from contextlib import suppress
from typing import IO, TYPE_CHECKING

from contree_sdk.compat import Self
from contree_sdk.execution import OperationContext
from contree_sdk.session.base import encode_stdin_chunk, instance_result, stream_repr_for_stdin, write_stream_chunk
from contree_sdk.session.contracts import OperationContract, SubprocessContract


if TYPE_CHECKING:
    from contree_client.models import InstanceResult, OperationEvent, OperationResponse
    from contree_client.types import ContreeSyncClient


DEFAULT_SHUTDOWN_SIGNAL = "SIGTERM"
SHUTDOWN_POLL_INTERVAL = 0.1


class Operation(OperationContract):
    """Handle to a spawned instance operation, identified by its UUID."""

    def __init__(
        self,
        client: ContreeSyncClient,
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
        # destination paths already uploaded for this spawn (set by ContreeSession.spawn(),
        # so commit_result() can record them without uploading the same content again)
        self.context = context
        self.files = context.files if context is not None else files
        self.response: OperationResponse | None = None
        self.queues: dict[int, queue.Queue[OperationEvent | None]] = {}
        # events for a spid `run()` hasn't registered a queue for yet - the pump
        # thread can race ahead of run() and observe a spid's events (including its
        # own exit) before the caller gets a chance to claim them; buffering here and
        # flushing on registration (see claim_queue()) closes that race
        self.pending_events: dict[int, queue.Queue[OperationEvent]] = {}
        self.terminal = False
        self.stream_error: Exception | None = None
        self.consumer_thread: threading.Thread | None = None
        self.lock = threading.Lock()

    def events(self, *, since: int | None = None, spid: int | None = None) -> Iterator[OperationEvent]:
        return self.client.follow_operation_events(self.uuid, since=since, spid=spid)

    def status(self, *, inflight: bool = False) -> OperationResponse:
        self.response = self.client.get_operation_status(self.uuid, inflight=inflight)
        return self.response

    def send_stdin(self, data: str | bytes, *, spid: int = 1, close: bool = True) -> None:
        value, encoding = encode_stdin_chunk(data)
        self.client.operation_subprocess_stdin(self.uuid, spid, value, encoding=encoding, close=close)

    def signal(self, sig: str | None = None, *, spid: int = 1) -> None:
        self.client.operation_subprocess_kill(self.uuid, spid, signal=sig)

    def cancel(self) -> None:
        self.client.cancel_operation(self.uuid)

    def wait(self, *, timeout: float | None = None) -> InstanceResult:
        try:
            self.response = self.client.wait_operation(
                self.uuid, timeout=timeout if timeout is not None else self.timeout
            )
        except BaseException:
            with suppress(Exception):
                self.cancel()
            raise
        return instance_result(self.response)

    def __enter__(self) -> Self:
        with self.lock:
            if self.consumer_thread is None:
                self.consumer_thread = threading.Thread(target=self.pump, daemon=True)
                self.consumer_thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            self.shutdown()
        else:
            with suppress(Exception):
                self.shutdown()

    def pump(self) -> None:
        # single background reader for the whole operation's event stream (unfiltered:
        # a server-side spid filter would also drop the operation-wide `completion`
        # event, since `completion` carries no spid at all), demultiplexed by spid
        # into whichever queue `run()` registered for that spid - or buffered in
        # pending_events if run() hasn't registered one yet (see __init__)
        try:  # noqa: PLW0717 - one event stream must have one error and cleanup boundary
            for event in self.events():
                if event.type == "completion":
                    break
                spid = event.spid
                if not isinstance(spid, int) or spid == 1:
                    continue
                with self.lock:
                    target = self.queues.get(spid)
                    if target is None:
                        self.pending_events.setdefault(spid, queue.Queue()).put(event)
                        continue
                target.put(event)
        except Exception as error:
            self.stream_error = error
        finally:
            with self.lock:
                self.terminal = True
                queues = list(self.queues.values())
            for target in queues:
                target.put(None)

    def claim_queue(self, spid: int) -> queue.Queue[OperationEvent | None]:
        # registers spid's queue, flushing anything pump() buffered for it before this
        # call could run; if the operation already ended, closes the handle immediately
        # so a subprocess whose exit raced ahead of this registration doesn't hang forever
        subprocess_queue: queue.Queue[OperationEvent | None] = queue.Queue()
        with self.lock:
            buffered = self.pending_events.pop(spid, None)
            if buffered is not None:
                while not buffered.empty():
                    subprocess_queue.put(buffered.get_nowait())
            if self.terminal:
                subprocess_queue.put(None)
            else:
                self.queues[spid] = subprocess_queue
        return subprocess_queue

    def run(
        self,
        command: str,
        *,
        shell: bool = False,
        args: Iterable[str] = (),
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        stdin: str | bytes | None = None,
        truncate_output_at: int | None = None,
    ) -> SubprocessContract:
        if self.consumer_thread is None:
            raise RuntimeError("Operation.run() requires the operation to be used as a context manager ('with')")
        stdin_repr = stream_repr_for_stdin(stdin) if stdin is not None else ...
        spid = self.client.operation_subprocess_create(
            self.uuid,
            command,
            args=list(args) if args else ...,
            shell=shell,
            env=env if env is not None else ...,
            cwd=cwd if cwd is not None else ...,
            stdin=stdin_repr,
            truncate_output_at=truncate_output_at if truncate_output_at is not None else ...,
        )
        return self.create_subprocess(spid, self.claim_queue(spid))

    def create_subprocess(self, spid: int, events_queue: queue.Queue[OperationEvent | None]) -> SubprocessContract:
        """Create a subprocess handle. Override to return a custom implementation.

        Returns:
            A handle consuming the supplied event queue.

        """
        return SubprocessHandle(self, spid, events_queue)

    def shutdown(self) -> None:
        try:
            if self.stream_error is not None:
                self.cancel()
            elif not self.terminal:
                try:
                    self.signal(DEFAULT_SHUTDOWN_SIGNAL)
                    deadline = time.monotonic() + self.shutdown_timeout
                    while time.monotonic() < deadline and not self.terminal:
                        time.sleep(SHUTDOWN_POLL_INTERVAL)
                finally:
                    if not self.terminal:
                        self.cancel()
        finally:
            if self.consumer_thread is not None:
                self.consumer_thread.join(timeout=self.shutdown_timeout)
        if self.stream_error is not None:
            raise self.stream_error


class SubprocessHandle(SubprocessContract):
    """Both blocking-waitable (final result) and iterable (live events) for one spid."""

    def __init__(self, operation: Operation, spid: int, events_queue: queue.Queue[OperationEvent | None]) -> None:
        self.operation = operation
        self.spid = spid
        self.queue = events_queue
        self.finished = False
        self.result: InstanceResult | None = None

    def __iter__(self) -> Iterator[OperationEvent]:
        while not self.finished:
            item = self.queue.get()
            if item is None:
                self.finished = True
                if self.operation.stream_error is not None:
                    raise self.operation.stream_error
                return
            if item.type == "exit":
                self.finished = True
            yield item

    def wait(self, *, timeout: float | None = None) -> InstanceResult:
        deadline = None if timeout is None else time.monotonic() + timeout
        while not self.finished:
            remaining: float | None = None
            if deadline is not None:
                remaining = max(0.0, deadline - time.monotonic())
                if remaining <= 0:
                    raise TimeoutError(f"subprocess spid={self.spid} did not exit within {timeout}s")
            try:
                item = self.queue.get(timeout=remaining)
            except queue.Empty:
                raise TimeoutError(f"subprocess spid={self.spid} did not exit within {timeout}s") from None
            if item is None or item.type == "exit":
                self.finished = True
                if item is None and self.operation.stream_error is not None:
                    raise self.operation.stream_error
        if self.result is None:
            self.result = self.operation.client.operation_subprocess(self.operation.uuid, self.spid)
        return self.result

    def pipe_to(
        self, *, stdout: IO[str] | IO[bytes] | None = None, stderr: IO[str] | IO[bytes] | None = None
    ) -> InstanceResult:
        for event in self:
            if event.type == "stdout" and stdout is not None:
                write_stream_chunk(stdout, event.data)
            elif event.type == "stderr" and stderr is not None:
                write_stream_chunk(stderr, event.data)
        if self.result is None:
            self.result = self.operation.client.operation_subprocess(self.operation.uuid, self.spid)
        return self.result
