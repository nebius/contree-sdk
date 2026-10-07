"""Asynchronous commands sharing a VM until a policy requests a snapshot."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from contextlib import suppress
from math import isfinite

from contree_client.models import InstanceResult, OperationEvent

from contree_sdk.compat import Self
from contree_sdk.execution import AsyncExecutor, RunRequest
from contree_sdk.session.asyncio import ContreeAsyncSession
from contree_sdk.session.contracts import AsyncOperationContract, AsyncSubprocessContract
from contree_sdk.session.lazy_state import LazyPhase, LazyState
from contree_sdk.session.snapshot_policy import AbstractSnapshotPolicy, IdleSnapshotPolicy, SnapshotEvent
from contree_sdk.store import HistoryEntry


class AsyncLazySession(AsyncExecutor):
    """Share one VM across commands; save one history entry per snapshot.

    The supplied session, its client and its store remain caller-owned. Do not
    mutate that session outside this wrapper while a VM is active. Use this
    object as a context manager or call close/abort to release its worker.
    """

    def __init__(
        self,
        session: ContreeAsyncSession,
        *,
        snapshot_policy: AbstractSnapshotPolicy | None = None,
        snapshot_timeout: float = 30,
    ) -> None:
        if not isfinite(snapshot_timeout) or snapshot_timeout <= 0:
            raise ValueError("snapshot_timeout must be positive")
        self.session = session
        self.session_id = session.session_id
        self.snapshot_policy = snapshot_policy if snapshot_policy is not None else IdleSnapshotPolicy(60)
        self.snapshot_timeout = snapshot_timeout
        self.state = LazyState()
        self.condition = asyncio.Condition()
        self.operation: AsyncOperationContract | None = None
        self.worker: asyncio.Task[None] | None = None
        self.last_entry: HistoryEntry | None = None
        self._snapshot_future: Future[None] | None = None
        self._changed = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def phase(self) -> LazyPhase:
        return self.state.phase

    @property
    def error(self) -> BaseException | None:
        return self.state.error

    def prepare_request(self, request: RunRequest) -> RunRequest:
        """Apply the wrapped session's policy and validate shared-VM semantics.

        Returns:
            The effective request.

        Raises:
            ValueError: The request needs a disposable VM or unsupported live uploads.

        """
        request = self.session.prepare_request(request)
        if request.disposable:
            raise ValueError("LazySession commands cannot be disposable; use a separate ContreeAsyncSession")
        if (
            request.files
            or request.preserve_env
            or request.hostname is not None
            or request.resources_limits is not None
            or request.networking is not None
        ):
            raise ValueError(
                "files, preserve_env, hostname, resources_limits and networking require VM startup configuration"
            )
        return request

    def keepalive_request(self) -> RunRequest:  # noqa: PLR6301 - public extension hook
        """Supply a long-running main process available in the base image.

        Returns:
            The non-disposable request used to start each VM.

        """
        return RunRequest(command="sleep", args=("2147483647",), disposable=False)

    async def observe(self, event: OperationEvent | None, error: Exception | None) -> None:
        """Observe the operation's sole reader without depending on handle.wait()."""
        async with self.condition:
            previous_phase = self.state.phase
            if self.state.observe(event, error):
                self.snapshot_policy.notify(SnapshotEvent.COMMAND_FINISHED)
            self._notify()
            if previous_phase not in {"closed", "failed"} and isinstance(self.state.error, Exception):
                raise self.state.error

    def _notify(self) -> None:
        self.condition.notify_all()
        self._changed.set()

    def _policy_ready(self, future: Future[None]) -> None:
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._changed.set)

    def _snapshot_requested(self) -> bool:
        future = self._snapshot_future
        if future is None or not future.done():
            return False
        future.result()
        return True

    async def _start(self) -> None:
        self.state.begin()
        self.snapshot_policy.notify(SnapshotEvent.RESET)
        self._snapshot_future = self.snapshot_policy.should_snapshot()
        self._loop = asyncio.get_running_loop()
        self._snapshot_future.add_done_callback(self._policy_ready)
        self.operation = await self.session.spawn_request(self.keepalive_request())
        context = self.operation.context
        if context is None or context.request.disposable:
            raise ValueError("the keepalive factory must create a bound, non-disposable operation")
        self.operation.add_observer(self.observe)
        await self.operation.__aenter__()  # noqa: PLC2801 - context spans several commands
        self.state.phase = "running"
        if self.worker is None:
            self.worker = asyncio.create_task(self._control(), name=f"lazy-{self.session_id}")

    async def _admit_and_spawn(
        self, request: RunRequest
    ) -> tuple[AsyncOperationContract, AsyncSubprocessContract, float | None]:
        await self.session.ensure_ready()
        request = self.prepare_request(request)
        stdin = await self.session.file_transfer.read_stdin(request.stdin) if request.stdin is not None else None
        async with self.condition:
            while True:
                self.state.check()
                starting = self.state.phase == "cold"
                if starting:
                    try:
                        await self._start()
                    except BaseException as error:
                        self.state.fail(error)
                        self._notify()
                        raise
                if self.state.phase == "running":
                    if not starting:
                        try:
                            self.state.wants_snapshot(self._snapshot_requested())
                        except BaseException as error:
                            self.state.fail(error)
                            self._notify()
                            raise
                    if self.state.phase == "running":
                        break
                self._notify()
                await self.condition.wait()
            operation = self.operation
            if operation is None:
                raise RuntimeError("running LazySession has no operation")
            self.state.reserve()
            try:
                self.snapshot_policy.notify(SnapshotEvent.COMMAND_STARTED)
                handle = await operation.run(
                    request.title,
                    shell=request.shell is not None,
                    args=request.args,
                    env=dict(request.env) if request.env is not None else None,
                    cwd=request.cwd,
                    uid=request.uid,
                    gid=request.gid,
                    stdin=stdin,
                    stdin_open=request.stdin_open,
                    truncate_output_at=request.truncate_output_at,
                )
            except BaseException as error:
                self.state.creating -= 1
                self.state.fail(error)
                self._notify()
                raise
            self.state.created(handle.spid)
            self._notify()
            return operation, handle, request.timeout_seconds

    async def _spawn(self, request: RunRequest) -> tuple[AsyncOperationContract, AsyncSubprocessContract, float | None]:
        try:
            return await self._admit_and_spawn(request)
        except BaseException:
            if self.state.error is not None:
                self.snapshot_policy.notify(SnapshotEvent.CLOSE)
            if self.state.error is not None and self.operation is not None:
                with suppress(Exception):
                    await self.operation.cancel()
                with suppress(Exception):
                    await self.operation.shutdown()
            raise

    async def spawn_request(self, request: RunRequest) -> AsyncSubprocessContract:
        """Start a subprocess; track its exit even if the caller never waits.

        Returns:
            The subprocess handle from the operation factory.

        """
        return (await self._spawn(request))[1]

    async def spawn(self, command: str | None = None, **kwargs) -> AsyncSubprocessContract:
        return await self.spawn_request(
            RunRequest(command=command, disposable=kwargs.pop("disposable", False), **kwargs)
        )

    async def execute(self, request: RunRequest) -> InstanceResult:
        operation, handle, timeout = await self._spawn(request)
        try:
            result = await handle.wait(timeout=timeout)
        except BaseException:
            with suppress(Exception):
                await asyncio.shield(operation.signal("SIGKILL", spid=handle.spid))
            raise
        async with self.condition:
            if self.state.error is not None:
                raise RuntimeError("LazySession failed while executing a command") from self.state.error
        return result

    async def run(self, command: str | None = None, **kwargs) -> InstanceResult:
        """Run a shared-VM command. Options are RunRequest fields; disposable defaults to False.

        Returns:
            The subprocess result, including a nonzero exit code.

        """
        return await self.execute(RunRequest(command=command, disposable=kwargs.pop("disposable", False), **kwargs))

    async def _save(self, operation: AsyncOperationContract) -> None:
        await operation.signal("SIGTERM")
        await operation.wait(timeout=self.snapshot_timeout)
        await operation.shutdown()
        async with self.condition:
            if self.state.error is not None:
                raise RuntimeError("event stream failed during snapshot") from self.state.error
        entry = await self.session.commit_result(operation, title="LazySession snapshot")
        if entry is None:
            raise RuntimeError("commit policy rejected the LazySession snapshot")
        async with self.condition:
            self.last_entry = entry
            self.operation = None
            self.snapshot_policy.notify(SnapshotEvent.RESET)
            self._snapshot_future = None
            self.state.saved()
            self._notify()

    async def _control(self) -> None:
        try:  # noqa: PLW0717 - one failure boundary owns the worker lifecycle
            while True:
                async with self.condition:
                    self._changed.clear()
                    if self.state.phase in {"closed", "failed"}:
                        return
                    previous_phase = self.state.phase
                    if self.state.wants_snapshot(self._snapshot_requested()):
                        operation = self.operation
                        if operation is None:
                            raise RuntimeError("snapshot has no operation")  # noqa: TRY301 - fail the worker
                        self.state.phase = "snapshotting"
                    else:
                        operation = None
                    if self.state.phase != previous_phase:
                        self.condition.notify_all()
                if operation is None:
                    await self._changed.wait()
                else:
                    await self._save(operation)
        except BaseException as error:
            async with self.condition:
                self.state.fail(error)
                self._notify()
            if self.operation is not None:
                with suppress(Exception):
                    await self.operation.cancel()
                with suppress(Exception):
                    await self.operation.shutdown()
        finally:
            self.snapshot_policy.notify(SnapshotEvent.CLOSE)

    async def snapshot(self, *, timeout: float | None = None) -> HistoryEntry | None:
        """Drain accepted commands, save their common image, and reopen admission.

        timeout limits this wait; an already requested snapshot continues.
        Errors remain available as error and are raised on subsequent calls.

        Returns:
            The saved history entry, or None if no VM has run yet.

        Raises:
            RuntimeError: Saving failed or the wrapper is closed.
            TimeoutError: The caller's wait expired; saving continues in the worker.

        """
        async with self.condition:
            self.state.check()
            if self.state.phase == "cold":
                return self.last_entry
            generation = self.state.snapshots
            if self.state.phase == "running":
                self.state.phase = "draining"
            self._notify()
            try:
                await asyncio.wait_for(
                    self.condition.wait_for(lambda: self.state.snapshots != generation or self.state.error is not None),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                raise TimeoutError("LazySession snapshot is still pending") from None
            if self.state.error is not None:
                raise RuntimeError("LazySession snapshot failed") from self.state.error
            return self.last_entry

    async def close(self, *, timeout: float | None = None) -> None:
        """Save pending work and close this wrapper, retaining caller-owned resources.

        Raises:
            RuntimeError: Saving failed; the cause is available as error.
            TimeoutError: The caller's wait expired; closing continues in the worker.

        """
        async with self.condition:
            if self.state.phase == "closed":
                return
            self.state.closing = True
            if self.state.phase == "cold":
                self.state.phase = "closed"
                self.snapshot_policy.notify(SnapshotEvent.CLOSE)
            elif self.state.phase == "running":
                self.state.phase = "draining"
            self._notify()
            try:
                await asyncio.wait_for(
                    self.condition.wait_for(lambda: self.state.phase in {"closed", "failed"}), timeout=timeout
                )
            except asyncio.TimeoutError:
                raise TimeoutError("LazySession close is still pending") from None
            error = self.state.error
        if error is not None:
            with suppress(Exception):
                await self.abort()
            raise RuntimeError("LazySession close could not save pending work") from error
        if self.worker is not None:
            await asyncio.shield(self.worker)

    async def abort(self) -> None:
        """Discard unsaved work and close. An already running snapshot finishes first."""
        async with self.condition:
            await self.condition.wait_for(lambda: self.state.phase != "snapshotting")
            operation = self.operation
            self.state.closing = True
            self.state.phase = "closed"
            self.snapshot_policy.notify(SnapshotEvent.CLOSE)
            self._notify()
        try:
            if operation is not None:
                try:
                    await operation.cancel()
                finally:
                    try:
                        await operation.shutdown()
                    except Exception as error:
                        if error is not self.state.error:
                            raise
        finally:
            if self.worker is not None:
                await asyncio.shield(self.worker)

    async def read_file(self, path: str) -> bytes:
        async with self.condition:
            self._boundary()
            return await self.session.read_file(path)

    def _boundary(self) -> None:
        self.state.check()
        if self.state.phase != "cold":
            raise RuntimeError("snapshot pending work before reading files or changing history")

    async def create_branch(self, name: str, *, from_branch: str | None = None) -> None:
        async with self.condition:
            self._boundary()
            await self.session.create_branch(name, from_branch=from_branch)

    async def switch_branch(self, name: str) -> None:
        async with self.condition:
            self._boundary()
            await self.session.switch_branch(name)

    async def rollback(self, steps: int = 1) -> None:
        async with self.condition:
            self._boundary()
            await self.session.rollback(steps)

    async def __aenter__(self) -> Self:
        async with self.condition:
            self.state.check()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            await self.close()
        else:
            with suppress(Exception):
                await self.abort()
