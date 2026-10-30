from __future__ import annotations

import time
from collections.abc import Iterable, Mapping
from contextlib import suppress
from dataclasses import replace
from datetime import timedelta
from math import ceil
from typing import cast

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

from contree_sdk.execution import OperationContext, RunRequest, SyncExecutor
from contree_sdk.files import ClientFileTransfer, InputSource, RunFiles, StagedFile, SyncFileTransfer
from contree_sdk.inspection import ImageInspector
from contree_sdk.session.base import exit_code_of, instance_result, new_session_id, require_str, stream_repr_for_stdin
from contree_sdk.session.cleanup import owned_operation
from contree_sdk.session.commit_policy import AbstractCommitPolicy, ApiSuccessCommitPolicy
from contree_sdk.session.contracts import OperationContract
from contree_sdk.session.detached import decode_response, operation_context, operation_record
from contree_sdk.session.models import HistoryEntry
from contree_sdk.session.operation_sync import Operation
from contree_sdk.session.records import OperationRecord
from contree_sdk.session.tree import entry_from_node, entry_node, order_entries
from contree_sdk.store import JSONValue, Node, NodeConflictError, SyncMemoryStore, SyncStore
from contree_sdk.store.tree import DEFAULT_PAGE_SIZE, MAX_NODE_BATCH_SIZE


class ContreeSession(SyncExecutor):  # noqa: PLR0904 - public extension contract
    """A durable, resumable ConTree session backed by a Store (sync)."""

    def __init__(
        self,
        client: ContreeSyncClient,
        *,
        image: str | None = None,
        session_id: str | None = None,
        node_id: str | None = None,
        tree_kind: str = "session",
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
        self.cwd_override = cwd
        self.env_override = env
        self.cwd = cwd
        self.env = dict(env or {})
        self._active_branch = "main"
        self._branches: dict[str, str] = {}
        self._position_version = 0
        self.tip_id = ""
        self.image_uuid = ""
        self._initialize(image, node_id, tree_kind)

    def stage_files(self, files: RunFiles) -> HistoryEntry:
        parent_id = self.tip_id
        version = self._position_version
        image_uuid, cwd, env = self.image_uuid, self.cwd, dict(self.env)
        branch = self._active_branch
        attachments = tuple(
            (StagedFile.from_spec(path, spec) for path, spec in (self.file_transfer.prepare_files(files) or {}).items())
        )
        if not attachments:
            raise ValueError("staging requires files")
        node = entry_node(
            parent_id=parent_id,
            image_uuid=image_uuid,
            kind="stage",
            created_at=time.time(),
            attachments=attachments,
            cwd=cwd,
            env=env,
        )
        self.store.append(self.session_id, node)
        entry = entry_from_node(self.session_id, node)
        if self._branches.get(branch) == parent_id:
            self._branches[branch] = node.id
        if self.tip_id == parent_id and self._position_version == version:
            self._branches[self._active_branch] = node.id
            self.refresh_from_entry(entry)
        return entry

    def pending_files(self, node_id: str | None = None) -> tuple[StagedFile, ...]:
        node_id = self.tip_id if node_id is None else node_id
        pending = {}
        seen = set()
        cursor = None
        while True:
            page = self.store.list_history(
                self.session_id, node_id, limit=1 if cursor is None else DEFAULT_PAGE_SIZE, cursor=cursor
            )
            for node in page.items:
                for item in cast("list[dict]", node.data.get("attachments", [])):
                    attachment = StagedFile(**item)
                    if attachment.path not in seen:
                        pending[attachment.path] = attachment
                        seen.add(attachment.path)
                seen.update(cast("list[str]", node.data.get("applied_files", [])))
                if node.data.get("staging_complete") is True:
                    return tuple(pending[path] for path in sorted(pending))
            cursor = page.next_cursor
            if cursor is None:
                return tuple(pending[path] for path in sorted(pending))

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
        disposable: bool = False,
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
        record = self._register_operation(self.create_operation_record(operation))
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
        record = self.get_operation(operation_uuid)
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
        records = []
        cursor = None
        while True:
            page = self.store.list_nodes(
                self.session_id, kind="operation-pending", limit=MAX_NODE_BATCH_SIZE, cursor=cursor
            )
            pending = [
                OperationRecord.from_dict(cast("dict[str, JSONValue]", node.data["record"])) for node in page.items
            ]
            completed = (
                self.store.get_nodes(self.session_id, tuple(record.node_id for record in pending)) if pending else ()
            )
            for record, node in zip(pending, completed, strict=True):
                if node is not None:
                    record = OperationRecord.from_dict(cast("dict[str, JSONValue]", node.data["record"]))
                if not pending_only or record.pending:
                    records.append(record)
            cursor = page.next_cursor
            if cursor is None:
                return tuple(sorted(records, key=lambda record: record.uuid))

    def _finish_detached(self, operation: OperationContract) -> OperationRecord:
        record = self.get_operation(operation.uuid)
        self.check_operation_endpoint(record)
        if not record.pending:
            return record
        response = operation.response
        if response is None:
            raise ValueError("operation has no response; wait first")
        image_uuid = None
        exit_code = None
        context = self.restore_operation_context(record)
        if response.status == OperationStatus.SUCCESS:
            result = instance_result(response)
            if not record.disposable and self.commit_policy.should_commit(context, result):
                image_uuid = require_str(response.result_image_uuid, "operation returned no result image")
                exit_code = exit_code_of(result)
        elif response.status not in {OperationStatus.FAILED, OperationStatus.CANCELLED}:
            raise ValueError("operation is not complete")
        node_id = record.node_id
        completed = replace(record, response=response.to_dict(), history_id=node_id if image_uuid else None)
        node = entry_node(
            node_id=node_id,
            parent_id=record.parent_id,
            image_uuid=image_uuid,
            kind="run" if image_uuid else "operation-result",
            created_at=record.created_at,
            title=record.title,
            operation_uuid=record.uuid,
            exit_code=exit_code,
            files=record.files,
            applied_files=record.files,
            cwd=context.session_cwd,
            env=dict(context.session_env),
            payload={"record": completed.to_dict(), "staging_complete": image_uuid is not None},
        )
        try:
            self.store.append(self.session_id, node)
        except NodeConflictError:
            return self.get_operation(record.uuid)
        return completed

    def wait_operation(
        self,
        operation_uuid: str,
        *,
        timeout: float | None = None,
        branch: str | None = None,
    ) -> InstanceResult:
        """Wait and finish once, without switching the session's active branch.

        Completed outcomes are replayed locally. Transport errors remain pending.
        Late results retain their original parent without replacing newer local
        positions. The first completed outcome wins across concurrent policies.

        Returns:
            The stored process result, including nonzero exit codes.

        """
        version = self._position_version
        record = self.get_operation(operation_uuid)
        self.check_operation_endpoint(record)
        was_pending = record.pending
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
            record = self._finish_detached(operation)
        if branch is not None and record.history_id is not None:
            self._branches[branch] = record.history_id
        if was_pending and record.history_id is not None:
            entry = self.get_entry(record.history_id)
            if self._branches.get(record.branch) == record.parent_id:
                self._branches[record.branch] = entry.id
            if (
                self.tip_id == record.parent_id
                and self._active_branch == record.branch
                and self._position_version == version
            ):
                self.refresh_from_entry(entry)
        return instance_result(decode_response(record))

    def commit_result(
        self,
        operation: OperationContract,
        *,
        title: str | None = None,
        branch: str | None = None,
        files: tuple[str, ...] | None = None,
        data: dict[str, JSONValue] | None = None,
    ) -> HistoryEntry | None:
        context = operation.context
        if context is None or context.session_id != self.session_id:
            raise ValueError("operation does not belong to this session")
        if context.detached:
            if files is not None or (title is not None and title != context.request.title):
                raise ValueError("detached metadata is fixed at registration")
            record = self._finish_detached(operation)
            instance_result(decode_response(record))
            if record.history_id is None:
                return None
            entry = self.get_entry(record.history_id)
            if self._branches.get(record.branch) == record.parent_id:
                self._branches[record.branch] = entry.id
            if (
                self.tip_id == record.parent_id
                and self._active_branch == record.branch
                and self._position_version == context.position_version
            ):
                self.refresh_from_entry(entry)
            return entry
        response = operation.response
        if response is None:
            raise ValueError("operation has no response; wait first")
        result = instance_result(response)
        if context.request.disposable or not self.commit_policy.should_commit(context, result):
            return None
        node = entry_node(
            node_id=context.node_id,
            parent_id=context.parent_id,
            image_uuid=require_str(response.result_image_uuid, "operation returned no result image"),
            kind="run",
            created_at=context.created_at,
            title=title if title is not None else context.request.title,
            operation_uuid=operation.uuid,
            exit_code=exit_code_of(result),
            files=files if files is not None else context.files,
            applied_files=context.files,
            payload={"staging_complete": True},
            user=data,
            cwd=context.session_cwd,
            env=dict(context.session_env),
        )
        self.store.append(self.session_id, node)
        entry = entry_from_node(self.session_id, node)
        if context.branch is not None and self._branches.get(context.branch) == context.parent_id:
            self._branches[context.branch] = node.id
        if branch is not None:
            self._branches[branch] = node.id
            self._active_branch = branch
            self.refresh_from_entry(entry)
        elif (
            self.tip_id == context.parent_id
            and self._active_branch == context.branch
            and (self._position_version == context.position_version)
        ):
            self._branches[self._active_branch] = node.id
            self.refresh_from_entry(entry)
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
        disposable: bool = False,
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
        self._save_configuration()

    def set_env(self, updates: dict[str, str | None]) -> None:
        for key, value in updates.items():
            if value is None:
                self.env.pop(key, None)
            else:
                self.env[key] = value
        self._save_configuration()

    def create_branch(self, name: str, *, from_branch: str | None = None) -> None:
        if not name or name in self._branches:
            raise ValueError("branch name is empty or already exists")
        if from_branch is not None and from_branch not in self._branches:
            raise ValueError("unknown source branch")
        self._branches[name] = self._branches[from_branch] if from_branch else self.tip_id

    def switch_branch(self, name: str) -> None:
        if name not in self._branches:
            raise ValueError("unknown local branch")
        entry = self.get_entry(self._branches[name])
        self._active_branch = name
        self._position_version += 1
        self.refresh_from_entry(entry)

    def list_branches(self) -> list[tuple[str, bool]]:
        return [(name, name == self._active_branch) for name in sorted(self._branches)]

    def delete_branch(self, name: str) -> None:
        if name == self._active_branch:
            raise ValueError("cannot delete the selected local branch")
        if name not in self._branches:
            raise ValueError("unknown local branch")
        del self._branches[name]

    def rollback(self, steps: int = 1) -> None:
        if steps < 0:
            raise ValueError("steps must be nonnegative")
        node = self.store.get_node(self.session_id, self.tip_id)
        for _ in range(steps):
            if node.parent_id is None:
                raise ValueError("cannot roll back beyond the root")
            node = self.store.get_node(self.session_id, node.parent_id)
        self.navigate(node.id)

    def navigate(self, node_id: str) -> None:
        entry = self.get_entry(node_id)
        self._position_version += 1
        self._branches[self._active_branch] = entry.id
        self.refresh_from_entry(entry)

    def navigate_forward(self, steps: int = 1) -> None:
        if steps < 0:
            raise ValueError("steps must be nonnegative")
        node_id = self.tip_id
        for _ in range(steps):
            children = []
            cursor = None
            while True:
                page = self.store.list_children(self.session_id, node_id, cursor=cursor)
                children.extend(node for node in page.items if node.data.get("image_uuid"))
                cursor = page.next_cursor
                if cursor is None:
                    break
            if len(children) != 1:
                raise ValueError("forward requires exactly one continuation; navigate to an explicit node")
            node_id = children[0].id
        self.navigate(node_id)

    def history(self) -> tuple[list[HistoryEntry], dict[str, list[str]]]:
        entries = [
            entry_from_node(self.session_id, node)
            for node in self._all_nodes()
            if node.data.get("image_uuid") and node.kind != "operation-pending"
        ]
        names = {}
        for name, node_id in self._branches.items():
            names.setdefault(node_id, []).append(name)
        return (order_entries(entries), names)

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

    def create_inspector(self, image_uuid: str) -> ImageInspector:
        """Create a view of one image. Override to customize inspection.

        Returns:
            An inspector borrowing the client's connection and file transfer.

        """
        return ImageInspector(self.client, image_uuid, self.file_transfer)

    def inspect(self) -> ImageInspector:
        """Pin the current saved image without starting a VM.

        Pending staged attachments appear only after an operation applies them.

        Returns:
            A read-only view that borrows this session's client and file transfer.

        """
        image_uuid = require_str(self.image_uuid, "session has no resolved image")
        return self.create_inspector(image_uuid)

    def read_file(self, path: str) -> bytes:
        view = self.inspect()
        return view.read_file(path)

    def spawn_request(self, request: RunRequest) -> OperationContract:
        """Prepare and submit a command, then construct its operation through the factory.

        Returns:
            A bound operation whose context records the effective request.

        """
        request = self.prepare_request(request)
        image_uuid = require_str(self.image_uuid, "session has no resolved image")
        parent_id = self.tip_id
        position_version = self._position_version
        session_cwd, session_env = self.cwd, dict(self.env)
        branch = self._active_branch
        staged = self.pending_files(parent_id)
        files = {item.path: item.as_spec() for item in staged}
        files.update(self.file_transfer.prepare_files(request.files) or {})
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
            position_version=position_version,
            session_cwd=session_cwd,
            session_env=session_env,
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

    def _all_nodes(self, *, kind: str | None = None) -> list[Node]:
        result = []
        cursor = None
        while True:
            page = self.store.list_nodes(self.session_id, kind=kind, cursor=cursor)
            result.extend(page.items)
            cursor = page.next_cursor
            if cursor is None:
                return result

    def _initialize(self, image: str | None, node_id: str | None, tree_kind: str) -> None:
        info = self.store.get_session(self.session_id)
        if info is None:
            if image is None:
                raise ValueError("unknown session; provide an image to create it")
            self.store.create_session(self.session_id, kind=tree_kind)
        roots = self.store.list_children(self.session_id, None).items
        if not roots:
            if image is None:
                raise ValueError("session has no root image")
            root = entry_node(
                parent_id=None,
                image_uuid=self.resolve_image(image),
                kind="init",
                created_at=time.time(),
                cwd=self.cwd,
                env=self.env,
            )
            try:
                self.store.append(self.session_id, root)
            except NodeConflictError:
                roots = self.store.list_children(self.session_id, None).items
                if not roots:
                    raise
        if node_id is None:
            nodes = self._all_nodes()
            entries = [
                node
                for node in nodes
                if isinstance(node.data.get("image_uuid"), str) and node.kind != "operation-pending"
            ]
            parents = {node.parent_id for node in entries}
            leaves = [node for node in entries if node.id not in parents]
            if len(leaves) != 1:
                raise ValueError("session has multiple continuations; provide node_id explicitly")
            node = leaves[0]
        else:
            node = self.store.get_node(self.session_id, node_id)
        self.refresh_from_entry(entry_from_node(self.session_id, node))
        if self.cwd_override is None:
            self.cwd = cast("str | None", node.data.get("cwd"))
        if self.env_override is None:
            self.env = dict(cast("dict[str, str]", node.data.get("env", {})))
        self._branches = {"main": self.tip_id}

    def get_entry(self, node_id: str) -> HistoryEntry:
        return entry_from_node(self.session_id, self.store.get_node(self.session_id, node_id))

    def get_operation(self, operation_uuid: str) -> OperationRecord:
        pending = self.store.get_node(self.session_id, "operation-pending:" + operation_uuid)
        record = OperationRecord.from_dict(cast("dict[str, JSONValue]", pending.data["record"]))
        try:
            completed = self.store.get_node(self.session_id, record.node_id)
        except ValueError:
            return record
        return OperationRecord.from_dict(cast("dict[str, JSONValue]", completed.data["record"]))

    def _register_operation(self, record: OperationRecord) -> OperationRecord:
        node = Node(
            id="operation-pending:" + record.uuid,
            parent_id=record.parent_id,
            kind="operation-pending",
            data={"record": record.to_dict(), "operation_uuid": record.uuid},
        )
        self.store.append(self.session_id, node)
        return self.get_operation(record.uuid)

    def _save_configuration(self) -> None:
        node = entry_node(
            parent_id=self.tip_id,
            image_uuid=self.image_uuid,
            kind="config",
            created_at=time.time(),
            cwd=self.cwd,
            env=self.env,
        )
        self.store.append(self.session_id, node)
        self._branches[self._active_branch] = node.id
        self._position_version += 1
        self.refresh_from_entry(entry_from_node(self.session_id, node))
