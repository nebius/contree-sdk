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

import base64
import binascii
import queue
import threading
import time
from collections.abc import Iterable, Iterator
from io import TextIOBase
from typing import IO, TYPE_CHECKING, Any, Literal

from typing_extensions import Self

from contree_sdk.session.base import instance_result, stream_repr_for_stdin


if TYPE_CHECKING:
    from contree_client.models import InstanceResult, OperationEvent, OperationResponse
    from contree_client.types import ContreeSyncClient


DEFAULT_SHUTDOWN_SIGNAL = "SIGTERM"
SHUTDOWN_POLL_INTERVAL = 0.1


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


class Operation:
    """Handle to a spawned instance operation, identified by its UUID."""

    def __init__(
        self,
        client: ContreeSyncClient,
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
        # destination paths already uploaded for this spawn (set by ContreeSession.spawn(),
        # so commit_result() can record them without uploading the same content again)
        self.files = files
        self.response: OperationResponse | None = None
        self.queues: dict[int, queue.Queue[OperationEvent | None]] = {}
        self.terminal = False
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
        self.response = self.client.wait_operation(self.uuid, timeout=timeout if timeout is not None else self.timeout)
        return instance_result(self.response)

    def __enter__(self) -> Self:
        with self.lock:
            if self.consumer_thread is None:
                self.consumer_thread = threading.Thread(target=self.pump, daemon=True)
                self.consumer_thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.shutdown()

    def pump(self) -> None:
        # single background reader for the whole operation's event stream (unfiltered:
        # a server-side spid filter would also drop the operation-wide `completion`
        # event, since `completion` carries no spid at all), demultiplexed by spid
        # into whichever queue `run()` registered for that spid
        try:
            for event in self.client.follow_operation_events(self.uuid):
                if event.type == "completion":
                    break
                spid = event.spid
                if not isinstance(spid, int):
                    continue
                with self.lock:
                    target = self.queues.get(spid)
                if target is not None:
                    target.put(event)
        finally:
            with self.lock:
                self.terminal = True
                queues = list(self.queues.values())
            for target in queues:
                target.put(None)

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
    ) -> SubprocessHandle:
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
        subprocess_queue: queue.Queue[OperationEvent | None] = queue.Queue()
        with self.lock:
            self.queues[spid] = subprocess_queue
        return SubprocessHandle(self, spid, subprocess_queue)

    def shutdown(self) -> None:
        # graceful-then-forceful: signal spid=1, give it shutdown_timeout to reach a
        # terminal status (observed via the consumer thread), else force-cancel
        if not self.terminal:
            self.signal(DEFAULT_SHUTDOWN_SIGNAL)
            deadline = time.monotonic() + self.shutdown_timeout
            while time.monotonic() < deadline and not self.terminal:
                time.sleep(SHUTDOWN_POLL_INTERVAL)
            if not self.terminal:
                self.cancel()
        if self.consumer_thread is not None:
            self.consumer_thread.join(timeout=self.shutdown_timeout)


class SubprocessHandle:
    """Both blocking-waitable (final result) and iterable (live events) for one spid."""

    def __init__(self, operation: Operation, spid: int, events_queue: queue.Queue[OperationEvent | None]) -> None:
        self.operation = operation
        self.spid = spid
        self.queue = events_queue

    def __iter__(self) -> Iterator[OperationEvent]:
        while True:
            item = self.queue.get()
            if item is None:
                return
            yield item
            if item.type == "exit":
                return

    def wait(self, *, timeout: float | None = None) -> InstanceResult:
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
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
                break
        return self.operation.client.operation_subprocess(self.operation.uuid, self.spid)

    def pipe_to(
        self, *, stdout: IO[str] | IO[bytes] | None = None, stderr: IO[str] | IO[bytes] | None = None
    ) -> InstanceResult:
        for event in self:
            if event.type == "stdout" and stdout is not None:
                write_stream_chunk(stdout, event.data)
            elif event.type == "stderr" and stderr is not None:
                write_stream_chunk(stderr, event.data)
        return self.operation.client.operation_subprocess(self.operation.uuid, self.spid)
