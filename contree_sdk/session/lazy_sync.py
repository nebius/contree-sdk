"""Synchronous commands sharing a VM until a policy requests a snapshot."""

from __future__ import annotations

import threading
from collections.abc import Generator
from concurrent.futures import Future
from contextlib import closing, contextmanager, suppress
from math import isfinite
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from contree_client.exceptions import UnprocessableEntityError
from contree_client.models import InstanceResult, OperationEvent

from contree_sdk.compat import Self
from contree_sdk.exceptions import FileWriteError
from contree_sdk.execution import RunRequest, SyncExecutor
from contree_sdk.file_io import write_download
from contree_sdk.inspection import ImageInspector
from contree_sdk.session.base import require_str
from contree_sdk.session.contracts import OperationContract, SubprocessContract
from contree_sdk.session.defaults import (
    DEFAULT_IDLE_SNAPSHOT_SECONDS,
    DEFAULT_READINESS_TIMEOUT,
    DEFAULT_SNAPSHOT_TIMEOUT,
    KEEPALIVE_SLEEP_SECONDS,
)
from contree_sdk.session.lazy_state import LazyPhase, LazyState
from contree_sdk.session.models import HistoryEntry
from contree_sdk.session.snapshot_policy import AbstractSnapshotPolicy, IdleSnapshotPolicy, SnapshotEvent
from contree_sdk.session.sync import ContreeSession
from contree_sdk.utils.live_files import extract_download, pack_upload, ready_call, ready_stream, validate_remote_path
from contree_sdk.utils.models.file import UploadFileSpec


class LazySession(SyncExecutor):  # noqa: PLR0904 - public session, history and filesystem operations
    """Share one VM across commands; save one history entry per snapshot.

    The supplied session, its client and its store remain caller-owned. Do not
    mutate that session outside this wrapper while a VM is active. Use this
    object as a context manager or call close/abort to release its worker.
    """

    def __init__(
        self,
        session: ContreeSession,
        *,
        snapshot_policy: AbstractSnapshotPolicy | None = None,
        snapshot_timeout: float = DEFAULT_SNAPSHOT_TIMEOUT,
        startup_timeout: float = DEFAULT_READINESS_TIMEOUT,
        vm_request: RunRequest | None = None,
    ) -> None:
        if not isfinite(snapshot_timeout) or snapshot_timeout <= 0:
            raise ValueError("snapshot_timeout must be positive")
        if not isfinite(startup_timeout) or startup_timeout <= 0:
            raise ValueError("startup_timeout must be finite and positive")
        self.startup_timeout = startup_timeout
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
        self._startup_admission_pending = False
        self.condition = threading.Condition()
        self.operation: OperationContract | None = None
        self.worker: threading.Thread | None = None
        self.last_entry: HistoryEntry | None = None
        self._snapshot_future: Future[None] | None = None
        self._changed = threading.Event()

    @property
    def phase(self) -> LazyPhase:
        with self.condition:
            return self.state.phase

    @property
    def error(self) -> BaseException | None:
        with self.condition:
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
            raise ValueError("LazySession commands cannot be disposable; use a separate ContreeSession")
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

    def observe(self, event: OperationEvent | None, error: Exception | None) -> None:
        """Observe the operation's sole reader without depending on handle.wait()."""
        with self.condition:
            # The startup waiter owns failure reporting until the primary is ready.
            if self.state.phase == "starting":
                return
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
        self._changed.set()

    def _snapshot_requested(self) -> bool:
        future = self._snapshot_future
        if future is None or not future.done():
            return False
        future.result()
        return True

    def _start(self) -> None:
        self.state.begin_start()
        self._startup_admission_pending = True
        self.snapshot_policy.notify(SnapshotEvent.RESET)
        self._snapshot_future = self.snapshot_policy.should_snapshot()
        self._snapshot_future.add_done_callback(self._policy_ready)
        self.operation = self.session.spawn_request(self.keepalive_request())
        context = self.operation.context
        if context is None or context.request.disposable:
            raise ValueError("the keepalive factory must create a bound, non-disposable operation")
        self.operation.add_observer(self.observe)
        self.operation.__enter__()  # noqa: PLC2801 - context spans several commands
        self._notify()
        if self.worker is None:
            self.worker = threading.Thread(target=self._control, daemon=True, name=f"lazy-{self.session_id}")
            self.worker.start()

    def _get_running_operation_locked(self, *, start_vm: bool = True) -> OperationContract | None:
        # Caller holds the condition lock. A cold read returns None to use the saved image.
        started_here = False
        try:  # noqa: PLW0717 - one admission boundary records startup/policy failures
            while True:
                if started_here and self.state.error is not None:
                    raise self.state.error  # noqa: TRY301 - preserve the recorded startup failure
                self.state.ensure_usable()
                if self.state.phase == "cold" and not start_vm:
                    return None
                if self.state.phase == "cold":
                    started_here = True
                    self._start()
                if self.state.phase == "running":
                    # The work that started this VM gets its first admission.
                    if not started_here and self._startup_admission_pending:
                        self.condition.wait()
                        continue
                    if not started_here and self._snapshot_requested():
                        self.state.request_snapshot()
                    if self.state.phase == "running":
                        break
                self._notify()
                self.condition.wait()
        except BaseException as error:
            if (
                not self.state.closing
                and self.state.phase != "closed"
                and (started_here or (isinstance(error, Exception) and self.state.phase == "running"))
            ):
                self.state.fail(error)
                self._notify()
            raise
        self._startup_admission_pending = False
        operation = self.operation
        if operation is None:
            raise RuntimeError("running LazySession has no operation")
        return operation

    def _admit_and_spawn(self, request: RunRequest) -> tuple[OperationContract, SubprocessContract, float | None]:
        request = self.prepare_request(request)
        stdin = self.session.file_transfer.read_stdin(request.stdin) if request.stdin is not None else None
        with self.condition:
            operation = self._get_running_operation_locked()
            if operation is None:
                raise RuntimeError("command admission returned no VM")
            self.state.reserve()
            try:
                self.snapshot_policy.notify(SnapshotEvent.COMMAND_STARTED)
                handle = operation.run(
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

    def _spawn(self, request: RunRequest) -> tuple[OperationContract, SubprocessContract, float | None]:
        try:
            return self._admit_and_spawn(request)
        except BaseException:
            if self.state.error is not None:
                self.snapshot_policy.notify(SnapshotEvent.CLOSE)
            if self.state.error is not None and self.operation is not None:
                with suppress(Exception):
                    self.operation.cancel()
                with suppress(Exception):
                    self.operation.shutdown()
            raise

    def spawn_request(self, request: RunRequest) -> SubprocessContract:
        """Start a subprocess; track its exit even if the caller never waits.

        Returns:
            The subprocess handle from the operation factory.

        """
        return self._spawn(request)[1]

    def spawn(self, command: str | None = None, **kwargs) -> SubprocessContract:
        return self.spawn_request(RunRequest(command=command, disposable=kwargs.pop("disposable", False), **kwargs))

    def execute(self, request: RunRequest) -> InstanceResult:
        operation, handle, timeout = self._spawn(request)
        try:
            result = handle.wait(timeout=timeout)
        except BaseException:
            with suppress(Exception):
                operation.signal("SIGKILL", spid=handle.spid)
            raise
        with self.condition:
            if self.state.error is not None:
                raise RuntimeError("LazySession failed while executing a command") from self.state.error
        return result

    def run(self, command: str | None = None, **kwargs) -> InstanceResult:
        """Run a shared-VM command. Options are RunRequest fields; disposable defaults to False.

        Returns:
            The subprocess result, including a nonzero exit code.

        """
        return self.execute(RunRequest(command=command, disposable=kwargs.pop("disposable", False), **kwargs))

    def _save(self, operation: OperationContract) -> None:
        operation.signal("SIGTERM")
        operation.wait(timeout=self.snapshot_timeout)
        operation.shutdown()
        with self.condition:
            if self.state.error is not None:
                raise RuntimeError("event stream failed during snapshot") from self.state.error
        entry = self.session.commit_result(operation, title="LazySession snapshot")
        if entry is None:
            raise RuntimeError("commit policy rejected the LazySession snapshot")
        with self.condition:
            self.last_entry = entry
            self.operation = None
            self.snapshot_policy.notify(SnapshotEvent.RESET)
            self._snapshot_future = None
            self.state.finish_snapshot()
            self._notify()

    def _finish_start(self, operation: OperationContract) -> None:
        # Wait outside the condition: the shared reader also acquires it.
        operation.wait_ready(timeout=self.startup_timeout)
        with self.condition:
            if self.state.phase != "starting":
                return
            self.state.finish_start()
            self._notify()

    def _snapshot_operation_locked(self) -> OperationContract | None:
        if self._startup_admission_pending and self.state.phase == "running":
            return None
        previous_phase = self.state.phase
        if self._snapshot_requested():
            self.state.request_snapshot()
        if self.state.phase != previous_phase:
            self.condition.notify_all()
        if not self.state.ready_to_snapshot():
            return None
        operation = self.operation
        if operation is None:
            raise RuntimeError("snapshot has no operation")
        self.state.begin_snapshot()
        return operation

    def _control(self) -> None:
        try:  # noqa: PLW0717 - one failure boundary owns the worker lifecycle
            while True:
                with self.condition:
                    self._changed.clear()
                    if self.state.phase in {"closed", "failed"}:
                        return
                    starting = self.state.phase == "starting"
                    operation = self.operation if starting else self._snapshot_operation_locked()
                if operation is None:
                    self._changed.wait()
                elif starting:
                    self._finish_start(operation)
                else:
                    self._save(operation)
        except BaseException as error:
            with self.condition:
                if self.state.phase == "closed":
                    return
                self.state.fail(error)
                self._notify()
            if self.operation is not None:
                with suppress(Exception):
                    self.operation.cancel()
                with suppress(Exception):
                    self.operation.shutdown()
        finally:
            self.snapshot_policy.notify(SnapshotEvent.CLOSE)

    def snapshot(self, *, timeout: float | None = None) -> HistoryEntry | None:
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
        with self.condition:
            return self._snapshot_locked(timeout=timeout)

    def _snapshot_locked(self, *, timeout: float | None = None) -> HistoryEntry | None:
        self.state.ensure_usable()
        if self.state.phase == "cold":
            return self.last_entry
        generation = self.state.snapshots
        self.state.request_snapshot()
        self._notify()
        completed = self.condition.wait_for(
            lambda: self.state.snapshots != generation or self.state.error is not None or self.state.phase == "closed",
            timeout=timeout,
        )
        if not completed:
            raise TimeoutError("LazySession snapshot is still pending")
        if self.state.error is not None:
            raise RuntimeError("LazySession snapshot failed") from self.state.error
        if self.state.snapshots == generation:
            raise RuntimeError("LazySession closed before snapshot completed")
        return self.last_entry

    def close(self, *, timeout: float | None = None) -> None:
        """Save pending work and close this wrapper, retaining caller-owned resources.

        Raises:
            RuntimeError: Saving failed; the cause is available as error.
            TimeoutError: The caller's wait expired; closing continues in the worker.

        """
        with self.condition:
            if self.state.phase == "closed":
                return
            self.state.request_close()
            if self.state.phase == "closed":
                self.snapshot_policy.notify(SnapshotEvent.CLOSE)
            self._notify()
            completed = self.condition.wait_for(
                lambda: self.state.phase in {"closed", "failed"},
                timeout=timeout,
            )
            if not completed:
                raise TimeoutError("LazySession close is still pending")
            error = self.state.error
        if error is not None:
            with suppress(Exception):
                self.abort()
            raise RuntimeError("LazySession close could not save pending work") from error
        if self.worker is not None:
            self.worker.join()

    def abort(self) -> None:
        """Discard unsaved work and close. An already running snapshot finishes first."""
        with self.condition:
            self.condition.wait_for(lambda: self.state.phase != "snapshotting")
            operation = self.operation
            self.state.close()
            self.snapshot_policy.notify(SnapshotEvent.CLOSE)
            self._notify()
        try:
            if operation is not None:
                try:
                    operation.cancel()
                finally:
                    try:
                        operation.shutdown()
                    except Exception as error:
                        if error is not self.state.error:
                            raise
        finally:
            if self.worker is not None:
                self.worker.join()

    def inspect(self) -> ImageInspector:
        """Pin the selected saved image without stopping or starting a VM.

        Returns:
            An inspector borrowing the underlying client and file transfer.

        Raises:
            RuntimeError: A VM is active, or this session has failed or is closing/closed.

        """
        with self.condition:
            self.state.ensure_usable()
            if self.state.phase != "cold":
                raise RuntimeError("Live inspection is not supported; call snapshot() before inspect()")
            image_uuid = require_str(self.session.image_uuid, "session has no resolved image")
            return self.session.create_inspector(image_uuid)

    @contextmanager
    def _file_access(self, *, write: bool = False) -> Generator[tuple[str, bool], None, None]:
        reserved = False
        try:
            with self.condition:
                operation = self._get_running_operation_locked(start_vm=write)
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
                with self.condition:
                    self.state.transfers -= 1
                    if self.state.phase not in {"closed", "failed"}:
                        self.snapshot_policy.notify(SnapshotEvent.TRANSFER_FINISHED)
                    self._notify()
            elif self.state.error is not None and self.operation is not None:
                with suppress(Exception):
                    self.abort()

    def _apply_file(self, operation: str, source: Path | bytes, path: str, *, unpack: bool = False) -> None:
        uploaded = self.session.file_transfer.upload(UploadFileSpec(source=source, path=path))
        try:
            ready_call(
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

    def read_file(self, path: str) -> bytes:
        """Read live VM contents, or the selected image when no VM is running.

        Returns:
            Complete file contents. This does not request a snapshot.

        """
        validate_remote_path(path)
        with self._file_access() as (identifier, live):
            if live:
                return ready_call(lambda: self.session.client.inspect_instance_download(identifier, path))
            return self.session.file_transfer.read_file(identifier, path)

    def write_file(self, path: str, content: bytes) -> None:
        """Publish bytes in the live VM; start a VM if needed. Does not snapshot."""
        validate_remote_path(path)
        with self._file_access(write=True) as (identifier, _):
            self._apply_file(identifier, content, path)

    def upload_file(self, source: str | Path, path: str) -> None:
        """Upload a local regular file, preserving its permission bits.

        Raises:
            ValueError: The source is not a regular file or the destination has no filename.

        """
        validate_remote_path(path)
        destination = PurePosixPath(path)
        if not destination.name or not Path(source).is_file():
            raise ValueError("upload_file requires a regular source file and a destination filename")
        with self._file_access(write=True) as (identifier, _), TemporaryDirectory() as tmp:
            archive = Path(tmp) / "upload.tar.gz"
            pack_upload(Path(source), archive, name=destination.name)
            self._apply_file(identifier, archive, str(destination.parent), unpack=True)

    def upload_dir(self, source: str | Path, path: str) -> None:
        """Merge a local directory into the live VM, preserving unrelated entries.

        Raises:
            ValueError: The source is not a directory.

        """
        validate_remote_path(path)
        if not Path(source).is_dir():
            raise ValueError("upload_dir requires a source directory")
        with self._file_access(write=True) as (identifier, _), TemporaryDirectory() as tmp:
            archive = Path(tmp) / "upload.tar.gz"
            pack_upload(Path(source), archive)
            self._apply_file(identifier, archive, path, unpack=True)

    def download_file(self, path: str, destination: str | Path) -> int:
        """Atomically download a live or saved file without requesting a snapshot.

        Returns:
            Number of downloaded bytes.

        """
        validate_remote_path(path)
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        with self._file_access() as (identifier, live):
            if not live:
                return self.session.file_transfer.download_file(identifier, path, destination)
            with closing(
                ready_stream(lambda: self.session.client.inspect_instance_download_stream(identifier, path))
            ) as chunks:
                return write_download(
                    chunks, destination, path=path, on_progress=self.session.file_transfer.on_progress
                )

    def download_dir(self, path: str, destination: str | Path) -> None:
        """Download a live or saved directory as an archive; never snapshots."""
        validate_remote_path(path)
        with self._file_access() as (identifier, live), TemporaryDirectory() as tmp:
            archive = Path(tmp) / "download.tar"
            source = (
                ready_stream(lambda: self.session.client.inspect_instance_archive(identifier, path))
                if live
                else ready_stream(lambda: self.session.client.inspect_image_archive(identifier, path))
            )
            with closing(source) as chunks:
                write_download(chunks, archive, path=path)
            extract_download(archive, Path(destination))

    def _boundary(self) -> None:
        self.state.ensure_usable()
        if self.state.phase != "cold":
            raise RuntimeError("snapshot pending work before changing history")

    def create_branch(self, name: str, *, from_branch: str | None = None) -> None:
        with self.condition:
            self._boundary()
            self.session.create_branch(name, from_branch=from_branch)

    def switch_branch(self, name: str) -> None:
        with self.condition:
            self._boundary()
            self.session.switch_branch(name)

    def rollback(self, steps: int = 1) -> None:
        with self.condition:
            self._boundary()
            self.session.rollback(steps)

    def __enter__(self) -> Self:
        with self.condition:
            self.state.ensure_usable()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            self.close()
        else:
            with suppress(Exception):
                self.abort()
