"""Asynchronous commands sharing a VM until a policy requests a snapshot."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from concurrent.futures import Future
from contextlib import aclosing, asynccontextmanager, suppress
from math import isfinite
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from contree_client.exceptions import UnprocessableEntityError
from contree_client.models import InstanceResult, OperationEvent

from contree_sdk.compat import Self
from contree_sdk.exceptions import FileWriteError
from contree_sdk.execution import AsyncExecutor, RunRequest
from contree_sdk.file_io import run_file_io, write_download_async
from contree_sdk.inspection import AsyncImageInspector
from contree_sdk.live_files import (
    extract_download,
    pack_upload,
    ready_call_async,
    ready_stream_async,
    validate_remote_path,
)
from contree_sdk.session.asyncio import ContreeAsyncSession
from contree_sdk.session.base import require_str
from contree_sdk.session.cleanup import await_cleanup
from contree_sdk.session.contracts import AsyncOperationContract, AsyncSubprocessContract
from contree_sdk.session.defaults import (
    DEFAULT_IDLE_SNAPSHOT_SECONDS,
    DEFAULT_SNAPSHOT_TIMEOUT,
    KEEPALIVE_SLEEP_SECONDS,
)
from contree_sdk.session.lazy_state import LazyPhase, LazyState
from contree_sdk.session.models import HistoryEntry
from contree_sdk.session.snapshot_policy import AbstractSnapshotPolicy, IdleSnapshotPolicy, SnapshotEvent
from contree_sdk.stdin import read_stdin_async
from contree_sdk.store import HistoryEntry
from contree_sdk.utils.models.file import UploadFileSpec


class AsyncLazySession(AsyncExecutor):  # noqa: PLR0904 - public session, history and filesystem operations
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
        snapshot_timeout: float = DEFAULT_SNAPSHOT_TIMEOUT,
        vm_request: RunRequest | None = None,
    ) -> None:
        if not isfinite(snapshot_timeout) or snapshot_timeout <= 0:
            raise ValueError("snapshot_timeout must be positive")
        self.session = session
        self.session_id = session.session_id
        self.snapshot_policy = (
            snapshot_policy if snapshot_policy is not None else IdleSnapshotPolicy(DEFAULT_IDLE_SNAPSHOT_SECONDS)
        )
        self.snapshot_timeout = snapshot_timeout
        if vm_request is not None and vm_request.disposable:
            raise ValueError("the VM request must be non-disposable")
        self.vm_request = vm_request
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

    def keepalive_request(self) -> RunRequest:
        """Supply a long-running main process available in the base image.

        Returns:
            The non-disposable request used to start each VM.

        """
        return self.vm_request or RunRequest(command="sleep", args=(str(KEEPALIVE_SLEEP_SECONDS),), disposable=False)

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
        self.state.begin_start()
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
        self.state.finish_start()
        if self.worker is None:
            self.worker = asyncio.create_task(self._control(), name=f"lazy-{self.session_id}")

    async def _get_running_operation_locked(self, *, start_vm: bool = True) -> AsyncOperationContract | None:
        # Caller holds the condition lock. A cold read returns None to use the saved image.
        while True:
            self.state.ensure_usable()
            if self.state.phase == "cold" and not start_vm:
                return None
            started_here = self.state.phase == "cold"
            if started_here:
                try:
                    await self._start()
                except BaseException as error:
                    self.state.fail(error)
                    self._notify()
                    raise
            if self.state.phase == "running":
                # Admit the work that started this VM before considering another snapshot.
                if not started_here:
                    try:
                        if self._snapshot_requested():
                            self.state.request_snapshot()
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
        return operation

    async def _admit_and_spawn(
        self, request: RunRequest
    ) -> tuple[AsyncOperationContract, AsyncSubprocessContract, float | None]:
        await self.session.ensure_ready()
        request = self.prepare_request(request)
        stdin = await read_stdin_async(request.stdin) if request.stdin is not None else None
        async with self.condition:
            operation = await self._get_running_operation_locked()
            if operation is None:
                raise RuntimeError("command admission returned no VM")
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
            self.state.finish_snapshot()
            self._notify()

    async def _control(self) -> None:
        try:  # noqa: PLW0717 - one failure boundary owns the worker lifecycle
            while True:
                async with self.condition:
                    self._changed.clear()
                    if self.state.phase in {"closed", "failed"}:
                        return
                    previous_phase = self.state.phase
                    if self._snapshot_requested():
                        self.state.request_snapshot()
                    if self.state.ready_to_snapshot():
                        operation = self.operation
                        if operation is None:
                            raise RuntimeError("snapshot has no operation")  # noqa: TRY301 - fail the worker
                        self.state.begin_snapshot()
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
        """Drain accepted commands and transfers, save their common image, and reopen admission.

        Snapshots are lightweight and can run after every command. They stop
        the VM. An unchanged filesystem can return the same image UUID.
        timeout limits this wait; an already requested snapshot continues.
        Errors remain available as error and are raised on subsequent calls.
        Saving failure or a closed wrapper raises RuntimeError. A wait that
        expires raises TimeoutError; saving continues in the worker.

        Returns:
            The saved history entry, or None if no VM has run yet.

        """
        async with self.condition:
            return await self._snapshot_locked(timeout=timeout)

    async def _snapshot_locked(self, *, timeout: float | None = None) -> HistoryEntry | None:
        self.state.ensure_usable()
        if self.state.phase == "cold":
            return self.last_entry
        generation = self.state.snapshots
        self.state.request_snapshot()
        self._notify()
        try:
            await asyncio.wait_for(
                self.condition.wait_for(
                    lambda: (
                        self.state.snapshots != generation
                        or self.state.error is not None
                        or self.state.phase == "closed"
                    )
                ),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise TimeoutError("LazySession snapshot is still pending") from None
        if self.state.error is not None:
            raise RuntimeError("LazySession snapshot failed") from self.state.error
        if self.state.snapshots == generation:
            raise RuntimeError("LazySession closed before snapshot completed")
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
            self.state.request_close()
            if self.state.phase == "closed":
                self.snapshot_policy.notify(SnapshotEvent.CLOSE)
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
            self.state.close()
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

    async def inspect(self) -> AsyncImageInspector:
        """Pin the selected saved image without stopping or starting a VM.

        Returns:
            An inspector borrowing the underlying client and file transfer.

        Raises:
            RuntimeError: A VM is active, or this session has failed or is closing/closed.

        """
        async with self.condition:
            self.state.ensure_usable()
            if self.state.phase != "cold":
                raise RuntimeError("Live inspection is not supported; call snapshot() before inspect()")
            await self.session.ensure_ready()
            image_uuid = require_str(self.session.image_uuid, "session has no resolved image")
            return self.session.create_inspector(image_uuid)

    @asynccontextmanager
    async def _file_access(self, *, write: bool = False) -> AsyncGenerator[tuple[str, bool], None]:
        reserved = False
        try:
            await self.session.ensure_ready()
            async with self.condition:
                operation = await self._get_running_operation_locked(start_vm=write)
                live = operation is not None
                if operation is not None:
                    self.state.transfers += 1
                    reserved = True
                    self.snapshot_policy.notify(SnapshotEvent.TRANSFER_STARTED)
                    identifier = operation.uuid
                else:
                    identifier = require_str(self.session.image_uuid, "session has no resolved image")
            yield identifier, live
        finally:
            if reserved:
                await await_cleanup(self._release_file())
            elif self.state.error is not None and self.operation is not None:
                with suppress(Exception):
                    await await_cleanup(self.abort())

    async def _release_file(self) -> None:
        async with self.condition:
            self.state.transfers -= 1
            if self.state.phase not in {"closed", "failed"}:
                self.snapshot_policy.notify(SnapshotEvent.TRANSFER_FINISHED)
            self._notify()

    async def _apply_file(self, operation: str, source: Path | bytes, path: str, *, unpack: bool = False) -> None:
        uploaded = await self.session.file_transfer.upload(UploadFileSpec(source=source, path=path))
        try:
            await ready_call_async(
                lambda: self.session.client.apply_instance_file(
                    operation,
                    require_str(uploaded.uuid, "upload returned no file UUID"),
                    path,
                    replace=True,
                    unpack=unpack,
                    merge=unpack,
                )
            )
        except UnprocessableEntityError as error:
            raise FileWriteError(path, error.error) from error

    async def read_file(self, path: str) -> bytes:
        """Read live VM contents, or the selected image when no VM is running.

        Returns:
            Complete file contents. This does not request a snapshot.

        """
        validate_remote_path(path)
        async with self._file_access() as (identifier, live):
            if live:
                return await ready_call_async(lambda: self.session.client.inspect_instance_download(identifier, path))
            return await self.session.file_transfer.read_file(identifier, path)

    async def write_file(self, path: str, content: bytes) -> None:
        """Publish bytes in the live VM; start a VM if needed. Does not snapshot."""
        validate_remote_path(path)
        async with self._file_access(write=True) as (identifier, _):
            await self._apply_file(identifier, content, path)

    async def upload_file(self, source: str | Path, path: str) -> None:
        """Upload a local regular file, preserving its permission bits.

        Raises:
            ValueError: The source is not a regular file or the destination has no filename.

        """
        validate_remote_path(path)
        destination = PurePosixPath(path)
        if not destination.name or not await run_file_io(Path(source).is_file):
            raise ValueError("upload_file requires a regular source file and a destination filename")
        async with self._file_access(write=True) as (identifier, _):
            with TemporaryDirectory() as tmp:
                archive = Path(tmp) / "upload.tar.gz"
                await run_file_io(lambda: pack_upload(Path(source), archive, name=destination.name))
                await self._apply_file(identifier, archive, str(destination.parent), unpack=True)

    async def upload_dir(self, source: str | Path, path: str) -> None:
        """Merge a local directory into the live VM, preserving unrelated entries.

        Raises:
            ValueError: The source is not a directory.

        """
        validate_remote_path(path)
        if not await run_file_io(Path(source).is_dir):
            raise ValueError("upload_dir requires a source directory")
        async with self._file_access(write=True) as (identifier, _):
            with TemporaryDirectory() as tmp:
                archive = Path(tmp) / "upload.tar.gz"
                await run_file_io(pack_upload, Path(source), archive)
                await self._apply_file(identifier, archive, path, unpack=True)

    async def download_file(self, path: str, destination: str | Path) -> int:
        """Atomically download a live or saved file without requesting a snapshot.

        Returns:
            Number of downloaded bytes.

        """
        validate_remote_path(path)
        await run_file_io(lambda: Path(destination).parent.mkdir(parents=True, exist_ok=True))
        async with self._file_access() as (identifier, live):
            if not live:
                return await self.session.file_transfer.download_file(identifier, path, destination)
            async with aclosing(
                ready_stream_async(lambda: self.session.client.inspect_instance_download_stream(identifier, path))
            ) as chunks:
                return await write_download_async(
                    chunks, destination, path=path, on_progress=self.session.file_transfer.on_progress
                )

    async def download_dir(self, path: str, destination: str | Path) -> None:
        """Download a live or saved directory as an archive; never snapshots."""
        validate_remote_path(path)
        async with self._file_access() as (identifier, live):
            with TemporaryDirectory() as tmp:
                archive = Path(tmp) / "download.tar"
                source = (
                    ready_stream_async(lambda: self.session.client.inspect_instance_archive(identifier, path))
                    if live
                    else self.session.client.inspect_image_archive(identifier, path)
                )
                async with aclosing(source) as chunks:
                    await write_download_async(chunks, archive, path=path)
                await run_file_io(extract_download, archive, Path(destination))

    def _boundary(self) -> None:
        self.state.ensure_usable()
        if self.state.phase != "cold":
            raise RuntimeError("snapshot pending work before changing history")

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
            self.state.ensure_usable()
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            await self.close()
        else:
            with suppress(Exception):
                await self.abort()
