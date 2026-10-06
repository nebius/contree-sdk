"""A fixed VM lifetime for agent environments and other long-lived consumers."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, AsyncIterator
from contextlib import suppress
from dataclasses import dataclass, field
from math import isfinite
from typing import Protocol

from contree_client.models import InstanceResult, OperationEvent

from contree_sdk.compat import Self
from contree_sdk.execution import RunRequest
from contree_sdk.session.asyncio import ContreeAsyncSession
from contree_sdk.session.contracts import AsyncOperationContract, AsyncSubprocessContract
from contree_sdk.session.lazy_async import AsyncLazySession
from contree_sdk.session.snapshot_policy import AbstractSnapshotPolicy, SnapshotEvent
from contree_sdk.session.stdin import DEFAULT_STDIN_CHUNK_SIZE, StdinResult
from contree_sdk.store import HistoryEntry


def default_vm_request() -> RunRequest:
    return RunRequest(command="sleep", args=("2147483647",), disposable=False)


@dataclass(frozen=True, kw_only=True)
class RuntimeOptions:
    """VM startup configuration and bounded shutdown waits.

    vm_request supplies the main process and VM-only options, including files,
    hostname, resource limits, and networking. Its timeout is the server's VM
    lifetime limit; each command has a separate local RunRequest timeout.
    """

    vm_request: RunRequest = field(default_factory=default_vm_request)
    stop_timeout: float = 30
    terminate_timeout: float = 5

    def __post_init__(self) -> None:
        if self.vm_request.disposable:
            raise ValueError("runtime VM requests must be non-disposable")
        for value in (self.stop_timeout, self.terminate_timeout):
            if not isfinite(value) or value <= 0:
                raise ValueError("runtime timeouts must be finite and positive")


class ManualSnapshotPolicy(AbstractSnapshotPolicy):
    """Retain a VM until an explicit lifecycle request; never schedule a snapshot."""

    def notify(self, event: SnapshotEvent) -> None:
        super().notify(event)


class AsyncRuntime(ABC):
    """Independent contract for a VM that remains alive until explicit stop.

    Construction and context entry do not start a VM. start/spawn/execute may
    start it. Stop is terminal; a stopped runtime must never restart itself.
    The caller owns the session, client, and injected components.
    """

    @property
    @abstractmethod
    def operation_uuid(self) -> str | None: ...

    @property
    @abstractmethod
    def error(self) -> BaseException | None: ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def spawn_request(self, request: RunRequest) -> AsyncSubprocessContract: ...

    @abstractmethod
    async def execute(self, request: RunRequest) -> InstanceResult: ...

    @abstractmethod
    async def terminate(self, spid: int) -> None: ...

    @abstractmethod
    async def send_stdin(self, data: str | bytes, *, spid: int, close: bool = True) -> None: ...

    @abstractmethod
    async def pipe_stdin(
        self,
        chunks: AsyncIterable[str | bytes],
        *,
        spid: int,
        close: bool = True,
        chunk_size: int = DEFAULT_STDIN_CHUNK_SIZE,
    ) -> StdinResult: ...

    @abstractmethod
    def events(self, *, spid: int | None = None, timeout: float | None = None) -> AsyncIterator[OperationEvent]: ...

    @abstractmethod
    async def stop(self, *, snapshot: bool = False) -> HistoryEntry | None: ...

    async def run(self, command: str | None = None, **kwargs) -> InstanceResult:
        return await self.execute(RunRequest(command=command, disposable=kwargs.pop("disposable", False), **kwargs))

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            await self.stop()
        else:
            with suppress(Exception):
                await self.stop()


class AsyncRuntimeFactory(Protocol):
    """Replace the runtime implementation without inheriting a concrete Session."""

    def __call__(self, session: ContreeAsyncSession, *, options: RuntimeOptions | None = None) -> AsyncRuntime: ...


class RuntimeLifecycle(AsyncLazySession):
    """Reuse LazySession admission, event observation, snapshot, and shutdown."""

    def __init__(self, session: ContreeAsyncSession, options: RuntimeOptions) -> None:
        super().__init__(session, snapshot_policy=ManualSnapshotPolicy(), snapshot_timeout=options.stop_timeout)
        self.options = options

    def keepalive_request(self) -> RunRequest:
        return self.options.vm_request

    async def start(self) -> None:
        try:  # noqa: PLW0717 - one cleanup boundary owns partial VM startup
            await self.session.ensure_ready()
            async with self.condition:
                self.state.check()
                if self.state.phase == "cold":
                    try:
                        await self._start()
                    except BaseException as error:
                        self.state.fail(error)
                        self._notify()
                        raise
        except BaseException:
            with suppress(Exception):
                await self.abort()
            raise

    async def terminate(self, operation: AsyncOperationContract, spid: int, timeout: float) -> None:
        async def kill_and_confirm() -> None:
            async with self.condition:
                if self.state.error is not None:
                    raise RuntimeError("runtime failed while terminating a command") from self.state.error
                if spid not in self.state.active or self.state.phase == "closed":
                    return
            await operation.signal("SIGKILL", spid=spid)
            async with self.condition:
                await self.condition.wait_for(lambda: spid not in self.state.active or self.state.error is not None)
                if self.state.error is not None:
                    raise RuntimeError("runtime failed while terminating a command") from self.state.error

        try:
            await asyncio.wait_for(kill_and_confirm(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError("subprocess exit was not confirmed before the termination timeout") from None


async def join_cleanup(task: asyncio.Task) -> None:
    """Finish lifecycle cleanup even when its caller receives repeated cancellation."""
    while not task.done():
        with suppress(asyncio.CancelledError):
            await asyncio.shield(task)
    task.result()


class ContreeAsyncRuntime(AsyncRuntime):
    """A fixed-lifetime runtime over caller-owned session and transport components.

    execute kills a timed-out or cancelled command and confirms its exit. If
    confirmation fails, the runtime fails and cancels the VM. Raw spawn handles
    remain caller-managed; use terminate when abandoning one of those handles.
    """

    def __init__(self, session: ContreeAsyncSession, *, options: RuntimeOptions | None = None) -> None:
        self.session = session
        self.options = options if options is not None else RuntimeOptions()
        self.lifecycle = self.create_lifecycle(session, self.options)
        self._start_task: asyncio.Task[None] | None = None
        self._stop_task: asyncio.Task[HistoryEntry | None] | None = None
        self._uuid: str | None = None
        self._processes: set[int] = set()
        self._failure: BaseException | None = None

    def create_lifecycle(self, session: ContreeAsyncSession, options: RuntimeOptions) -> RuntimeLifecycle:  # noqa: PLR6301
        return RuntimeLifecycle(session, options)

    @property
    def operation_uuid(self) -> str | None:
        return self._uuid

    @property
    def error(self) -> BaseException | None:
        return self._failure or self.lifecycle.error

    async def _start(self) -> None:
        try:
            await self.lifecycle.start()
        except BaseException as error:
            self._failure = error
            raise
        operation = self.lifecycle.operation
        if operation is None:
            raise RuntimeError("runtime startup returned no operation")
        self._uuid = operation.uuid

    async def start(self) -> None:
        if self._stop_task is not None:
            raise RuntimeError("runtime is stopping or stopped")
        if self._start_task is None:
            self._start_task = asyncio.create_task(self._start())
        try:
            await asyncio.shield(self._start_task)
            if self.error is not None:
                raise RuntimeError("runtime failed") from self.error
        except asyncio.CancelledError:
            cleanup = asyncio.create_task(self.stop())
            with suppress(Exception):
                await join_cleanup(cleanup)
            raise

    async def spawn_request(self, request: RunRequest) -> AsyncSubprocessContract:
        await self.start()
        handle = await self.lifecycle.spawn_request(request)
        self._processes.add(handle.spid)
        return handle

    async def execute(self, request: RunRequest) -> InstanceResult:
        timeout = request.timeout_seconds
        if timeout is not None and (not isfinite(timeout) or timeout <= 0):
            raise ValueError("command timeout must be finite and positive")
        await self.start()
        handle: AsyncSubprocessContract | None = None

        async def command() -> InstanceResult:
            nonlocal handle
            handle = await self.spawn_request(request)
            return await handle.wait()

        try:
            try:
                return await asyncio.wait_for(command(), timeout=timeout)
            except asyncio.TimeoutError:
                raise TimeoutError("runtime command did not complete before its timeout") from None
        except BaseException:
            if handle is not None:
                cleanup = asyncio.create_task(self.terminate(handle.spid))
                with suppress(Exception):
                    await join_cleanup(cleanup)
            raise

    def _operation(self, spid: int | None = None) -> AsyncOperationContract:
        if self._stop_task is not None:
            raise RuntimeError("runtime is stopping or stopped")
        if spid is not None and spid not in self._processes:
            raise ValueError("subprocess does not belong to this runtime")
        self.lifecycle.state.check()
        operation = self.lifecycle.operation
        if operation is None:
            raise RuntimeError("runtime has not started")
        return operation

    async def terminate(self, spid: int) -> None:
        if spid not in self._processes:
            raise ValueError("subprocess does not belong to this runtime")
        operation = self.lifecycle.operation
        if operation is None:
            return
        try:
            await self.lifecycle.terminate(operation, spid, self.options.terminate_timeout)
        except BaseException as error:
            self._failure = error
            cleanup = asyncio.create_task(self.stop())
            with suppress(Exception):
                await join_cleanup(cleanup)
            raise

    async def send_stdin(self, data: str | bytes, *, spid: int, close: bool = True) -> None:
        await self._operation(spid).send_stdin(data, spid=spid, close=close)

    async def pipe_stdin(
        self,
        chunks: AsyncIterable[str | bytes],
        *,
        spid: int,
        close: bool = True,
        chunk_size: int = DEFAULT_STDIN_CHUNK_SIZE,
    ) -> StdinResult:
        operation = self._operation(spid)
        try:
            return await operation.pipe_stdin(chunks, spid=spid, close=close, chunk_size=chunk_size)
        except BaseException:
            cleanup = asyncio.create_task(self.terminate(spid))
            with suppress(Exception):
                await join_cleanup(cleanup)
            raise

    def events(self, *, spid: int | None = None, timeout: float | None = None) -> AsyncIterator[OperationEvent]:
        return self._operation(spid).events(spid=spid, timeout=timeout)

    async def _stop(self, snapshot: bool) -> HistoryEntry | None:
        if self._start_task is not None:
            with suppress(Exception):
                await asyncio.shield(self._start_task)
        try:
            if snapshot:
                await self.lifecycle.close(timeout=self.options.stop_timeout)
                return self.lifecycle.last_entry
            await self.lifecycle.abort()
        except BaseException as error:
            self._failure = error
            with suppress(Exception):
                await self.lifecycle.abort()
            raise
        return None

    async def stop(self, *, snapshot: bool = False) -> HistoryEntry | None:
        """Stop once; concurrent calls share the first request's snapshot choice.

        Returns:
            A confirmed history entry when snapshot was requested, otherwise None.

        Raises:
            asyncio.CancelledError: The caller cancelled; cleanup has still finished.

        """
        if self._stop_task is None:
            self._stop_task = asyncio.create_task(self._stop(snapshot))
        try:
            return await asyncio.shield(self._stop_task)
        except asyncio.CancelledError:
            with suppress(Exception):
                await join_cleanup(self._stop_task)
            raise


def create_runtime(
    session: ContreeAsyncSession,
    *,
    options: RuntimeOptions | None = None,
    factory: AsyncRuntimeFactory = ContreeAsyncRuntime,
) -> AsyncRuntime:
    """Construct a runtime through an application-supplied factory.

    Returns:
        An unstarted runtime. The caller retains ownership of the session.

    """
    return factory(session, options=options)
