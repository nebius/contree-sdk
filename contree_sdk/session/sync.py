from __future__ import annotations

from collections.abc import Iterable
from contextlib import suppress
from dataclasses import replace
from datetime import timedelta
from math import ceil

from contree_client.models import ClosableStreamRepr, FileSpec, InstanceResult, InstanceSpawnResponse
from contree_client.types import ContreeSyncClient

from contree_sdk.exceptions import SessionConflictError
from contree_sdk.execution import OperationContext, RunRequest, SyncExecutor
from contree_sdk.files import ClientFileTransfer, InputSource, RunFiles, SyncFileTransfer, UploadFileSpec
from contree_sdk.session.base import exit_code_of, instance_result, new_session_id, require_str, stream_repr_for_stdin
from contree_sdk.session.contracts import OperationContract
from contree_sdk.session.operation_sync import Operation
from contree_sdk.store import HistoryEntry, SyncMemoryStore, SyncStore


class ContreeSession(SyncExecutor):  # noqa: PLR0904 - public extension contract
    """A durable, resumable ConTree session backed by a Store (sync)."""

    def __init__(
        self,
        client: ContreeSyncClient,
        *,
        image: str | None = None,
        session_id: str | None = None,
        store: SyncStore | None = None,
        file_transfer: SyncFileTransfer | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        if image is None and session_id is None:
            raise ValueError("either image or session_id must be provided")
        self.client = client
        self.store = store if store is not None else self.create_store()
        self.file_transfer = file_transfer if file_transfer is not None else self.create_file_transfer()
        self.session_id = session_id or new_session_id()
        metadata = self.store.get_session_metadata(self.session_id)
        self.cwd = cwd if cwd is not None else metadata.cwd
        self.env = env if env is not None else dict(metadata.env)

        tip = self.store.tip(self.session_id)
        if tip is not None:
            self.image_uuid = tip.image_uuid
            self.tip_id = tip.id
        elif image is not None:
            resolved = self.resolve_image(image)
            try:
                entry = self.store.append(
                    self.session_id, image_uuid=resolved, parent_id=None, kind="init", expected_tip=None
                )
            except SessionConflictError:
                entry = self.store.tip(self.session_id)
                if entry is None:
                    raise
            self.image_uuid = entry.image_uuid
            self.tip_id = entry.id
        else:
            raise ValueError(f"session {self.session_id!r} has no history and no image was given")

    def upload_file(self, file: UploadFileSpec) -> FileSpec:
        return self.file_transfer.upload(file)

    def build_files(self, files: RunFiles) -> dict[str, FileSpec] | None:
        return self.file_transfer.prepare_files(files)

    def spawn(
        self,
        command: str | None = None,
        *,
        shell: str | None = None,
        args: Iterable[str] = (),
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        stdin: InputSource | None = None,
        files: RunFiles = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
        preserve_env: bool = False,
        hostname: str | None = None,
    ) -> OperationContract:
        request = RunRequest(
            command=command,
            shell=shell,
            args=tuple(args),
            env=env,
            cwd=cwd,
            stdin=stdin,
            files=files,
            timeout=timeout,
            disposable=disposable,
            truncate_output_at=truncate_output_at,
            preserve_env=preserve_env,
            hostname=hostname,
        )
        return self.spawn_request(request)

    def commit_result(
        self,
        operation: OperationContract,
        *,
        title: str | None = None,
        branch: str | None = None,
        files: tuple[str, ...] | None = None,
    ) -> HistoryEntry:
        # append operation's result image to history - the "commit" step run() does inline;
        # files defaults to context.files (already uploaded by spawn()), pass an explicit
        # tuple only to override that record
        context = operation.context
        if context is None or context.session_id != self.session_id:
            raise ValueError("commit_result requires an operation spawned by this session")
        response = operation.response
        if response is None:
            raise ValueError("operation has no response yet; call wait() or status() before commit_result()")
        result_image_uuid = require_str(response.result_image_uuid, "operation succeeded but reported no result image")
        result = instance_result(response)
        entry = self.store.append(
            self.session_id,
            image_uuid=result_image_uuid,
            parent_id=context.parent_id,
            expected_tip=context.parent_id if branch is None or branch == context.branch else None,
            kind="run",
            title=title or "",
            operation_uuid=operation.uuid,
            exit_code=exit_code_of(result),
            branch=branch or context.branch,
            files=files if files is not None else context.files,
        )
        tip = (
            self.store.switch_branch(self.session_id, branch) if branch is not None else self.store.tip(self.session_id)
        )
        if tip is not None:
            self.tip_id = tip.id
            self.image_uuid = tip.image_uuid
        return entry

    def run(
        self,
        command: str | None = None,
        *,
        shell: str | None = None,
        args: Iterable[str] = (),
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        stdin: InputSource | None = None,
        files: RunFiles = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
        preserve_env: bool = False,
        hostname: str | None = None,
        branch: str | None = None,
    ) -> InstanceResult:
        request = RunRequest(
            command=command,
            shell=shell,
            args=tuple(args),
            env=env,
            cwd=cwd,
            stdin=stdin,
            files=files,
            timeout=timeout,
            disposable=disposable,
            truncate_output_at=truncate_output_at,
            preserve_env=preserve_env,
            hostname=hostname,
        )
        return self.execute(request, branch=branch)

    def refresh_from_entry(self, entry: HistoryEntry) -> None:
        self.tip_id = entry.id
        self.image_uuid = entry.image_uuid

    def set_cwd(self, cwd: str | None) -> None:
        self.cwd = cwd
        self.store.set_session_cwd(self.session_id, cwd)

    def set_env(self, updates: dict[str, str | None]) -> None:
        for key, value in updates.items():
            if value is None:
                self.env.pop(key, None)
            else:
                self.env[key] = value
        self.store.set_session_env(self.session_id, updates)

    def create_branch(self, name: str, *, from_branch: str | None = None) -> None:
        self.store.create_branch(self.session_id, name, from_branch=from_branch)

    def switch_branch(self, name: str) -> None:
        entry = self.store.switch_branch(self.session_id, name)
        self.refresh_from_entry(entry)

    def list_branches(self) -> list[tuple[str, bool]]:
        return self.store.list_branches(self.session_id)

    def delete_branch(self, name: str) -> None:
        self.store.delete_branch(self.session_id, name)

    def rollback(self, steps: int = 1) -> None:
        entry = self.store.rollback(self.session_id, steps)
        self.refresh_from_entry(entry)

    def navigate(self, target: int) -> None:
        entry = self.store.navigate(self.session_id, target)
        self.refresh_from_entry(entry)

    def navigate_forward(self, steps: int = 1) -> None:
        entry = self.store.navigate_forward(self.session_id, steps)
        self.refresh_from_entry(entry)

    def history(self) -> tuple[list[HistoryEntry], dict[int, list[str]]]:
        return self.store.history_dag(self.session_id)

    def create_store(self) -> SyncStore:  # noqa: PLR6301 - public extension contract
        """Create the default store when none was supplied.

        Returns:
            A new memory store owned by this session.

        """
        return SyncMemoryStore()

    def create_file_transfer(self) -> SyncFileTransfer:
        """Create file I/O when no component was supplied.

        Returns:
            A file-transfer component using the session client.

        """
        return ClientFileTransfer(self.client)

    def resolve_image(self, image: str) -> str:
        """Resolve a base image. Override to implement an import or registry policy.

        Returns:
            The resolved image UUID.

        """
        return self.client.resolve_image(image)

    def prepare_request(self, request: RunRequest) -> RunRequest:
        """Apply defaults before uploads or execution. Override to validate or transform commands.

        Returns:
            The effective command with session defaults applied.

        """
        return replace(
            request,
            env=request.env if request.env is not None else (self.env or None),
            cwd=request.cwd if request.cwd is not None else self.cwd,
        )

    def read_file(self, path: str) -> bytes:
        image_uuid = require_str(self.image_uuid, "session has no resolved image")
        return self.file_transfer.read_file(image_uuid, path)

    def spawn_request(self, request: RunRequest) -> OperationContract:
        """Prepare and submit a command, then construct its operation through the factory.

        Returns:
            A bound operation whose context records the effective request.

        """
        request = self.prepare_request(request)
        image_uuid = require_str(self.image_uuid, "session has no resolved image")
        parent_id = self.tip_id
        branch = self.store.active_branch(self.session_id)
        files = self.build_files(request.files)
        stdin = (
            stream_repr_for_stdin(self.file_transfer.read_stdin(request.stdin)) if request.stdin is not None else None
        )
        context = OperationContext(request, self.session_id, image_uuid, parent_id, branch, tuple(files or ()))
        response = self.submit_request(request, image_uuid, files=files, stdin=stdin)
        try:
            operation = self.create_operation(response, context)
            operation.context = context
        except BaseException:
            with suppress(Exception):
                self.client.cancel_operation(require_str(response.uuid, "missing operation uuid"))
            raise
        return operation

    def submit_request(
        self,
        request: RunRequest,
        image_uuid: str,
        *,
        files: dict[str, FileSpec] | None,
        stdin: ClosableStreamRepr | None,
    ) -> InstanceSpawnResponse:
        """Submit prepared input to the transport. Override for transport-level customization.

        Returns:
            The transport response identifying the spawned operation.

        """
        timeout = request.timeout_seconds
        return self.client.spawn_instance(
            request.title,
            image_uuid,
            disposable=request.disposable,
            shell=request.shell is not None,
            args=list(request.args),
            env=dict(request.env) if request.env is not None else ...,
            cwd=request.cwd if request.cwd is not None else ...,
            preserve_env=request.preserve_env,
            hostname=request.hostname if request.hostname is not None else ...,
            timeout=ceil(timeout) if timeout is not None else ...,
            truncate_output_at=request.truncate_output_at if request.truncate_output_at is not None else ...,
            files=files if files is not None else ...,
            stdin=stdin if stdin is not None else ...,
        )

    def create_operation(self, response: InstanceSpawnResponse, context: OperationContext) -> OperationContract:
        """Construct a lifecycle implementation bound to the supplied operation context.

        Returns:
            An implementation of the matching operation lifecycle contract.

        """
        uuid = require_str(response.uuid, "spawn_instance response missing operation uuid")
        return Operation(self.client, uuid, timeout=context.request.timeout_seconds, context=context)

    def execute(self, request: RunRequest, *, branch: str | None = None) -> InstanceResult:
        """Run a request to completion and commit its effective non-disposable result.

        Returns:
            The completed process result, including nonzero exit codes.

        Raises:
            ValueError: The operation factory returned an unbound operation.

        """
        operation = self.spawn_request(request)
        result = operation.wait()
        context = operation.context
        if context is None:
            raise ValueError("session operation has no context")
        if not context.request.disposable:
            self.commit_result(operation, title=context.request.title, branch=branch)
        return result
