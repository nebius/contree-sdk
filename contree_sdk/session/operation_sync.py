"""Operation lifecycle and subprocesses backed by one shared event reader."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Iterable, Iterator
from contextlib import suppress
from typing import IO

from contree_client.models import InstanceResult, OperationEvent, OperationResponse
from contree_client.types import ContreeSyncClient

from contree_sdk.compat import Self
from contree_sdk.execution import OperationContext
from contree_sdk.session.base import encode_stdin_chunk, instance_result, stream_repr_for_stdin, write_stream_chunk
from contree_sdk.session.contracts import OperationContract, OperationObserver, SubprocessContract
from contree_sdk.session.stdin import DEFAULT_STDIN_CHUNK_SIZE, StdinResult, stdin_chunks


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
        self.observers: list[OperationObserver] = []
        self.consumer_thread: threading.Thread | None = None
        self.lock = threading.Lock()
        self.history: list[OperationEvent] = []
        self.spawned: set[int] = set()
        self.exited: set[int] = set()
        self.completion_received = False
        self.entered = False
        self.changed = threading.Condition(self.lock)
        self.terminal_event = threading.Event()
        self.result_lock = threading.Lock()
        self.final_response: OperationResponse | None = None

    def add_observer(self, observer: OperationObserver) -> None:
        with self.lock:
            if self.consumer_thread is not None:
                raise RuntimeError("register observers before starting the event reader")
            self.observers.append(observer)

    def open_event_stream(self) -> Iterator[OperationEvent]:
        """Open the unfiltered source. Override this hook to supply custom events.

        Returns:
            The single transport stream consumed by the operation.

        """
        return self.client.follow_operation_events(self.uuid)

    def _start_reader(self) -> None:
        with self.lock:
            if self.consumer_thread is None:
                self.consumer_thread = threading.Thread(target=self.pump, daemon=True)
                self.consumer_thread.start()

    def events(
        self, *, since: int | None = None, spid: int | None = None, timeout: float | None = None
    ) -> Iterator[OperationEvent]:
        """Replay buffered events, then follow the shared reader with local filters.

        timeout bounds this subscription. Expiry does not cancel the operation.

        Yields:
            Events after ``since`` whose process matches ``spid``, when specified.

        Raises:
            TimeoutError: The subscription did not finish before timeout.

        """
        self._start_reader()
        deadline = None if timeout is None else time.monotonic() + timeout
        cursor = 0
        while True:
            with self.changed:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    raise TimeoutError(f"operation {self.uuid} events did not complete in time")
                if not self.changed.wait_for(
                    lambda cursor=cursor: cursor < len(self.history) or self.terminal_event.is_set(), timeout=remaining
                ):
                    raise TimeoutError(f"operation {self.uuid} events did not complete in time")
                if cursor == len(self.history):
                    if self.stream_error is not None:
                        raise self.stream_error
                    return
                event = self.history[cursor]
                cursor += 1
            if (since is None or event.id > since) and (spid is None or event.spid == spid):
                yield event

    def status(self, *, inflight: bool = False) -> OperationResponse:
        self.response = self.client.get_operation_status(self.uuid, inflight=inflight)
        return self.response

    def send_stdin(self, data: str | bytes, *, spid: int = 1, close: bool = True) -> None:
        value, encoding = encode_stdin_chunk(data)
        self.client.operation_subprocess_stdin(self.uuid, spid, value, encoding=encoding, close=close)

    def _process_ended(self, spid: int) -> bool:
        if self.stream_error is not None:
            raise self.stream_error
        return spid in self.exited or self.completion_received or self.terminal_event.is_set()

    def pipe_stdin(
        self,
        chunks: Iterable[str | bytes],
        *,
        spid: int = 1,
        close: bool = True,
        chunk_size: int = DEFAULT_STDIN_CHUNK_SIZE,
    ) -> StdinResult:
        """Forward chunks after spawn, using the operation's shared event reader.

        The caller owns the source and must make blocking reads interruptible.
        Use one writer per process. Errors cancel the operation and propagate.

        Returns:
            Acknowledged bytes, EOF delivery, and observed early completion.

        Raises:
            ValueError: chunk_size or spid is not positive.

        """
        if chunk_size <= 0 or spid < 1:
            raise ValueError("chunk_size and spid must be positive")
        try:
            return self._pipe_stdin(iter(chunks), spid, close=close, chunk_size=chunk_size)
        except BaseException:
            with suppress(Exception):
                self.cancel()
            raise

    def _pipe_stdin(self, chunks: Iterator[str | bytes], spid: int, *, close: bool, chunk_size: int) -> StdinResult:
        self._start_reader()
        with self.changed:
            self.changed.wait_for(lambda: spid in self.spawned or self._process_ended(spid))
        sent = 0
        while True:
            with self.changed:
                if self._process_ended(spid):
                    return StdinResult(sent, process_exited=True)
            try:
                data = next(chunks)
            except StopIteration:
                break
            for part in stdin_chunks(data, chunk_size):
                with self.changed:
                    if self._process_ended(spid):
                        return StdinResult(sent, process_exited=True)
                self.send_stdin(part, spid=spid, close=False)
                sent += len(part)
        with self.changed:
            if self._process_ended(spid):
                return StdinResult(sent, process_exited=True)
        if close:
            self.send_stdin(b"", spid=spid, close=True)
        return StdinResult(sent, eof_sent=close)

    def signal(self, sig: str | None = None, *, spid: int = 1) -> None:
        self.client.operation_subprocess_kill(self.uuid, spid, signal=sig)

    def cancel(self) -> None:
        self.client.cancel_operation(self.uuid)

    def wait(self, *, timeout: float | None = None) -> InstanceResult:
        try:
            self._start_reader()
            if not self.terminal_event.wait(self.timeout if timeout is None else timeout):
                raise TimeoutError(f"operation {self.uuid} did not complete in time")  # noqa: TRY301
            return self._completed_result()
        except BaseException:
            with suppress(Exception):
                self.cancel()
            raise

    def _completed_result(self) -> InstanceResult:
        if self.stream_error is not None:
            raise self.stream_error
        with self.result_lock:
            if self.final_response is None:
                self.final_response = self.status()
            return instance_result(self.final_response)

    def __enter__(self) -> Self:
        self.entered = True
        self._start_reader()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            self.shutdown()
        else:
            with suppress(Exception):
                self.shutdown()

    def _remember_event(self, event: OperationEvent) -> None:
        self.history.append(event)
        if event.type == "spawn" and isinstance(event.spid, int):
            self.spawned.add(event.spid)
        elif event.type == "exit" and isinstance(event.spid, int):
            self.exited.add(event.spid)
        elif event.type == "completion":
            self.completion_received = True

    def pump(self) -> None:
        # single background reader for the whole operation's event stream (unfiltered:
        # a server-side spid filter would also drop the operation-wide `completion`
        # event, since `completion` carries no spid at all), demultiplexed by spid
        # into whichever queue `run()` registered for that spid - or buffered in
        # pending_events if run() hasn't registered one yet (see __init__)
        source: Iterator[OperationEvent] | None = None
        try:  # noqa: PLW0717 - one event stream must have one error and cleanup boundary
            source = self.open_event_stream()
            for event in source:
                for observer in self.observers:
                    observer(event, None)
                with self.changed:
                    self._remember_event(event)
                    self.changed.notify_all()
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
            self._close_event_stream(source)
            for observer in self.observers:
                try:
                    observer(None, self.stream_error)
                except Exception as error:  # noqa: PERF203 - notify remaining observers after an error
                    if self.stream_error is None:
                        self.stream_error = error
            with self.changed:
                self.terminal = True
                for target in self.queues.values():
                    target.put(None)
                self.terminal_event.set()
                self.changed.notify_all()

    def _close_event_stream(self, source: Iterator[OperationEvent] | None) -> None:
        close = getattr(source, "close", None)
        if close is not None:
            try:
                close()
            except Exception as error:
                if self.stream_error is None:
                    self.stream_error = error

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
        stdin_open: bool = False,
        truncate_output_at: int | None = None,
    ) -> SubprocessContract:
        if not self.entered:
            raise RuntimeError("Operation.run() requires the operation to be used as a context manager ('with')")
        stdin_repr = (
            stream_repr_for_stdin(stdin or b"", close=not stdin_open) if stdin is not None or stdin_open else ...
        )
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
