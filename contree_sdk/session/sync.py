from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import suppress
from dataclasses import replace
from datetime import timedelta
from math import ceil

from contree_client.models import (
    ClosableStreamRepr,
    FileSpec,
    InstanceNetworking,
    InstanceResourcesLimits,
    InstanceResult,
    InstanceSpawnResponse,
    OperationStatus,
)
from contree_client.types import ContreeSyncClient

from contree_sdk.exceptions import SessionConflictError
from contree_sdk.execution import OperationContext, RunRequest, SyncExecutor
from contree_sdk.files import ClientFileTransfer, InputSource, RunFiles, SyncFileTransfer, UploadFileSpec
from contree_sdk.session.base import exit_code_of, instance_result, new_session_id, require_str, stream_repr_for_stdin
from contree_sdk.session.cleanup import owned_operation
from contree_sdk.session.commit_policy import AbstractCommitPolicy, ApiSuccessCommitPolicy
from contree_sdk.session.contracts import OperationContract
from contree_sdk.session.detached import decode_response, encode_response, operation_context, operation_record
from contree_sdk.session.operation_sync import Operation
from contree_sdk.store import HistoryEntry, StagedFile, SyncMemoryStore, SyncStore
from contree_sdk.store.operations import OperationRecord


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
        commit_policy: AbstractCommitPolicy | None = None,
    ) -> None:
        if image is None and session_id is None:
            raise ValueError("either image or session_id must be provided")
        self.client = client
        self.commit_policy = commit_policy if commit_policy is not None else ApiSuccessCommitPolicy()
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

    def stage_files(self, files: RunFiles) -> HistoryEntry:
        """Upload and persist attachments without starting a VM.

        Returns:
            The new staging history entry, which becomes the branch head.

        """
        parent_id = self.tip_id
        snapshot = self.store.read_session(self.session_id)
        branch = snapshot.summary().active_branch
        attachments = tuple(StagedFile.from_spec(path, spec) for path, spec in (self.build_files(files) or {}).items())
        entry = self.store.stage_files(
            self.session_id,
            attachments,
            branch=branch,
            expected_tip=parent_id,
        )
        tip = self.store.tip(self.session_id)
        if tip is not None:
            self.refresh_from_entry(tip)
        return entry

    def pending_files(self) -> tuple[StagedFile, ...]:
        """Read unapplied attachments at this session object's current history position.

        Returns:
            Attachments ordered by destination path.

        """
        return self.store.pending_files(self.session_id, history_id=self.tip_id)

    def spawn(
        self,
        command: str | None = None,
        *,
        shell: str | None = None,
        args: Iterable[str] = (),
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        stdin: InputSource | None = None,
        stdin_open: bool = False,
        files: RunFiles = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
        preserve_env: bool = False,
        hostname: str | None = None,
        uid: int | None = None,
        gid: int | None = None,
        resources_limits: InstanceResourcesLimits | None = None,
        networking: InstanceNetworking | None = None,
    ) -> OperationContract:
        request = RunRequest(
            command=command,
            shell=shell,
            args=tuple(args),
            env=env,
            cwd=cwd,
            stdin=stdin,
            stdin_open=stdin_open,
            files=files,
            timeout=timeout,
            disposable=disposable,
            truncate_output_at=truncate_output_at,
            preserve_env=preserve_env,
            hostname=hostname,
            uid=uid,
            gid=gid,
            resources_limits=resources_limits,
            networking=networking,
        )
        return self.spawn_request(request)

    def create_operation_record(self, operation: OperationContract) -> OperationRecord:
        """Serialize an operation context. Override to persist custom request fields.

        Returns:
            A pending record without local input sources.

        Raises:
            ValueError: The operation does not belong to this session.

        """
        context = operation.context
        if context is None or context.session_id != self.session_id:
            raise ValueError("detach requires an operation spawned by this session")
        return operation_record(operation.uuid, context, endpoint=str(self.client.base_url).rstrip("/"))

    def restore_operation_context(self, record: OperationRecord) -> OperationContext:  # noqa: PLR6301 - extension hook
        """Decode a stored request. Override together with create_operation_record.

        Returns:
            Its immutable source context, ready for an operation factory or policy.

        """
        return operation_context(record)

    def detach(self, operation: OperationContract) -> OperationRecord:
        """Register an already spawned operation without reading events or closing it.

        Returns:
            Its durable record. The caller still owns the live handle.

        Raises:
            ValueError: The operation does not belong to this session.

        """
        context = operation.context
        if context is None or context.session_id != self.session_id:
            raise ValueError("detach requires an operation spawned by this session")
        record = self.store.register_operation(self.create_operation_record(operation))
        operation.context = replace(context, detached=True)
        return record

    def spawn_detached(self, command: str | None = None, **kwargs) -> OperationRecord:
        """Spawn and register a command; options are RunRequest fields.

        Returns:
            A durable record whose UUID can be passed to wait_operation.

        """
        operation = self.spawn_request(RunRequest(command=command, **kwargs))
        try:
            return self.detach(operation)
        except BaseException:
            with suppress(Exception):
                operation.cancel()
            raise

    def restore_operation(self, operation_uuid: str) -> OperationContract:
        """Recreate a control handle from the persisted source context.

        Returns:
            An unentered handle. Use wait_operation to reuse a stored final result.

        """
        record = self.store.get_operation(self.session_id, operation_uuid)
        self.check_operation_endpoint(record)
        context = self.restore_operation_context(record)
        operation = self.create_operation(InstanceSpawnResponse(uuid=record.uuid), context)
        operation.context = context
        return operation

    def check_operation_endpoint(self, record: OperationRecord) -> None:
        """Check the recorded server before using an operation UUID.

        Raises:
            ValueError: The current client targets a different endpoint.

        """
        if record.endpoint != str(self.client.base_url).rstrip("/"):
            raise ValueError("registered operation belongs to a different endpoint")

    def list_operations(self, *, pending_only: bool = True) -> tuple[OperationRecord, ...]:
        """Read this session's durable operations.

        Returns:
            Records in UUID order, including completed ones when requested.

        """
        return self.store.list_operations(self.session_id, pending_only=pending_only)

    def _finish_detached(self, operation: OperationContract, *, branch: str | None = None) -> OperationRecord:
        record = self.store.get_operation(self.session_id, operation.uuid)
        self.check_operation_endpoint(record)
        if not record.pending:
            return record
        response = operation.response
        if response is None:
            raise ValueError("operation has no response yet; call wait() or status() first")
        image_uuid = None
        exit_code = None
        if response.status == OperationStatus.SUCCESS:
            result = instance_result(response)
            context = self.restore_operation_context(record)
            if not record.disposable and self.commit_policy.should_commit(context, result):
                image_uuid = require_str(response.result_image_uuid, "operation succeeded but reported no result image")
                exit_code = exit_code_of(result)
        elif response.status not in {OperationStatus.FAILED, OperationStatus.CANCELLED}:
            raise ValueError("operation is not complete")
        return self.store.finish_operation(
            self.session_id,
            record.uuid,
            encode_response(response),
            image_uuid=image_uuid,
            exit_code=exit_code,
            branch=branch,
        )

    def wait_operation(
        self,
        operation_uuid: str,
        *,
        timeout: float | None = None,
        branch: str | None = None,
    ) -> InstanceResult:
        """Wait and finish once, without switching the session's active branch.

        Completed outcomes are replayed locally. Transport errors remain pending.
        A tip conflict can be retried with a new branch name. The first completed
        outcome wins if callers use different policies concurrently.

        Returns:
            The stored process result, including nonzero exit codes.

        """
        record = self.store.get_operation(self.session_id, operation_uuid)
        self.check_operation_endpoint(record)
        if record.pending:
            operation = self.restore_operation(operation_uuid)
            with owned_operation(operation):
                try:
                    operation.wait(timeout=timeout)
                except BaseException as error:
                    response = operation.response
                    if response is not None and response.status in {OperationStatus.FAILED, OperationStatus.CANCELLED}:
                        try:
                            self._finish_detached(operation)
                        except Exception as save_error:
                            raise error from save_error
                    raise
            record = self._finish_detached(operation, branch=branch)
        tip = self.store.tip(self.session_id)
        if tip is not None:
            self.refresh_from_entry(tip)
        return instance_result(decode_response(record))

    def commit_result(
        self,
        operation: OperationContract,
        *,
        title: str | None = None,
        branch: str | None = None,
        files: tuple[str, ...] | None = None,
    ) -> HistoryEntry | None:
        """Apply the session commit policy to a completed operation.

        Returns:
            The new entry, or None for a disposable request or a rejected result.
            Rejection leaves branches, pending files, and session position unchanged.

        Raises:
            ValueError: The context, response, or accepted result image is missing.

        """
        context = operation.context
        if context is None or context.session_id != self.session_id:
            raise ValueError("commit_result requires an operation spawned by this session")
        response = operation.response
        if response is None:
            raise ValueError("operation has no response yet; call wait() or status() before commit_result()")
        if context.detached:
            if files is not None or (title is not None and title != context.request.title):
                raise ValueError("detached operation metadata is fixed at registration")
            record = self._finish_detached(operation, branch=branch)
            instance_result(decode_response(record))
            tip = self.store.tip(self.session_id)
            if tip is not None:
                self.refresh_from_entry(tip)
            return None if record.history_id is None else self.store.get_entry(self.session_id, record.history_id)
        result = instance_result(response)
        if context.request.disposable or not self.commit_policy.should_commit(context, result):
            return None
        result_image_uuid = require_str(response.result_image_uuid, "operation succeeded but reported no result image")
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
            applied_files=context.files,
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
        stdin_open: bool = False,
        files: RunFiles = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
        preserve_env: bool = False,
        hostname: str | None = None,
        uid: int | None = None,
        gid: int | None = None,
        resources_limits: InstanceResourcesLimits | None = None,
        networking: InstanceNetworking | None = None,
        branch: str | None = None,
    ) -> InstanceResult:
        request = RunRequest(
            command=command,
            shell=shell,
            args=tuple(args),
            env=env,
            cwd=cwd,
            stdin=stdin,
            stdin_open=stdin_open,
            files=files,
            timeout=timeout,
            disposable=disposable,
            truncate_output_at=truncate_output_at,
            preserve_env=preserve_env,
            hostname=hostname,
            uid=uid,
            gid=gid,
            resources_limits=resources_limits,
            networking=networking,
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

    def prepare_environment(self, env: Mapping[str, str] | None) -> dict[str, str] | None:
        """Overlay command variables on session defaults without mutating either input.

        Returns:
            A fresh mapping, or None when both inputs omit environment variables.

        """
        merged = {**self.env, **(env or {})}
        return merged if merged or env is not None else None

    def prepare_request(self, request: RunRequest) -> RunRequest:
        """Apply defaults before uploads or execution. Override to validate or transform commands.

        Returns:
            The effective command with session defaults applied.

        """
        return replace(
            request,
            env=self.prepare_environment(request.env),
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
        staged = self.store.pending_files(self.session_id, history_id=parent_id)
        files = {item.path: item.as_spec() for item in staged}
        files.update(self.build_files(request.files) or {})
        stdin = None
        if request.stdin is not None or request.stdin_open:
            data = self.file_transfer.read_stdin(request.stdin) if request.stdin is not None else b""
            stdin = stream_repr_for_stdin(data, close=not request.stdin_open)
        context = OperationContext(
            request,
            self.session_id,
            image_uuid,
            parent_id,
            branch,
            tuple(files or ()),
            tuple(StagedFile.from_spec(path, spec) for path, spec in files.items()),
        )
        response = self.submit_request(request, image_uuid, files=files or None, stdin=stdin)
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
            uid=request.uid if request.uid is not None else ...,
            gid=request.gid if request.gid is not None else ...,
            resources_limits=request.resources_limits if request.resources_limits is not None else ...,
            networking=request.networking if request.networking is not None else ...,
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
        with owned_operation(operation):
            result = operation.wait()
        context = operation.context
        if context is None:
            raise ValueError("session operation has no context")
        if not context.request.disposable:
            self.commit_result(operation, title=context.request.title, branch=branch)
        return result
