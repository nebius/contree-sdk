from __future__ import annotations

import time
from asyncio import Lock, shield
from collections.abc import Iterable, Mapping, Sequence
from contextlib import suppress
from dataclasses import replace
from datetime import timedelta
from math import ceil
from typing import Literal, cast

from contree_client.models import (
    ClosableStreamRepr,
    DirectoryList,
    FileSpec,
    GrepResult,
    InstanceNetworking,
    InstanceResourcesLimits,
    InstanceResult,
    InstanceSpawnResponse,
    OperationStatus,
)
from contree_client.types import ContreeAsyncClient

from contree_sdk.execution import AsyncExecutor, OperationContext, RunRequest
from contree_sdk.files import AsyncClientFileTransfer, AsyncFileTransfer, InputSource, RunFiles, StagedFile
from contree_sdk.inspection import AsyncImageInspector
from contree_sdk.session.base import exit_code_of, instance_result, new_session_id, require_str, stream_repr_for_stdin
from contree_sdk.session.cleanup import owned_async_operation
from contree_sdk.session.commit_policy import AbstractCommitPolicy, ApiSuccessCommitPolicy
from contree_sdk.session.contracts import AsyncOperationContract
from contree_sdk.session.detached import decode_response, operation_context, operation_record
from contree_sdk.session.models import HistoryEntry
from contree_sdk.session.operation_async import AsyncOperation
from contree_sdk.session.records import OperationRecord
from contree_sdk.session.tree import entry_from_node, entry_node, order_entries
from contree_sdk.store import AsyncMemoryStore, AsyncStore, JSONValue, Node, NodeConflictError
from contree_sdk.store.tree import DEFAULT_PAGE_SIZE, MAX_NODE_BATCH_SIZE


class PendingRun:
    """One-use execution wrapper. Await a result or enter an operation context."""

    def __init__(self, session: ContreeAsyncSession, request: RunRequest, *, branch: str | None = None) -> None:
        self.session = session
        self.request = request
        self.branch = branch
        self.operation: AsyncOperationContract | None = None
        self.started = False

    async def spawn(self) -> AsyncOperationContract:
        if self.started:
            raise RuntimeError("a PendingRun can only be used once")
        self.started = True
        self.operation = await self.session.spawn_request(self.request)
        return self.operation

    def __await__(self):
        return self.run_to_result().__await__()

    async def commit(self, operation: AsyncOperationContract) -> None:
        context = operation.context
        if context is None:
            raise ValueError("session operation has no context")
        if not context.request.disposable:
            await self.session.commit_result(operation, title=context.request.title, branch=self.branch)

    async def run_to_result(self) -> InstanceResult:
        operation = await self.spawn()
        async with owned_async_operation(operation):
            result = await operation.wait()
        await self.commit(operation)
        return result

    async def __aenter__(self) -> AsyncOperationContract:
        operation = await self.spawn()
        await operation.__aenter__()
        return operation

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        operation = self.operation
        if operation is None:
            return
        await operation.__aexit__(exc_type, exc, tb)
        if exc_type is None and operation.context is not None and not operation.context.request.disposable:
            response = await operation.status()
            if response.status == OperationStatus.SUCCESS:
                await self.commit(operation)


class ContreeAsyncSession(AsyncExecutor):  # noqa: PLR0904 - public extension contract
    """A durable, resumable ConTree session backed by a Store."""

    def __init__(
        self,
        client: ContreeAsyncClient,
        *,
        image: str | None = None,
        session_id: str | None = None,
        node_id: str | None = None,
        tree_kind: str = "session",
        store: AsyncStore | None = None,
        file_transfer: AsyncFileTransfer | None = None,
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
        self.image = image
        # constructor overrides win over store-persisted metadata; None means
        # "seed from the store once ensure_ready() can await it" (see below)
        self.cwd_override = cwd
        self.env_override = env
        self.cwd = cwd
        self.env: dict[str, str] = env if env is not None else {}
        self.image_uuid: str | None = None
        self.tip_id = ""
        self.node_id = node_id
        self.tree_kind = tree_kind
        self._active_branch = "main"
        self._branches: dict[str, str] = {}
        self._position_version = 0
        self.ready = False
        self.init_lock = Lock()

    async def ensure_ready(self) -> None:
        # double-checked locking: two concurrent first calls (e.g. two concurrent
        # .run()s on a fresh session) must not both observe ready=False and each
        # append their own "init" root entry to the store
        if self.ready:
            return
        async with self.init_lock:
            if self.ready:
                return
            await self._initialize(self.image, self.node_id, self.tree_kind)
            self.ready = True

    async def set_cwd(self, cwd: str | None) -> None:
        await self.ensure_ready()
        self.cwd = cwd
        await self._save_configuration()

    async def set_env(self, updates: dict[str, str | None]) -> None:
        await self.ensure_ready()
        for key, value in updates.items():
            if value is None:
                self.env.pop(key, None)
            else:
                self.env[key] = value
        await self._save_configuration()

    async def stage_files(self, files: RunFiles) -> HistoryEntry:
        await self.ensure_ready()
        parent_id = self.tip_id
        version = self._position_version
        image_uuid, cwd, env = self.image_uuid, self.cwd, dict(self.env)
        branch = self._active_branch
        prepared = await self.file_transfer.prepare_files(files)
        attachments = tuple(StagedFile.from_spec(path, spec) for path, spec in (prepared or {}).items())
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
        await self.store.append(self.session_id, node)
        entry = entry_from_node(self.session_id, node)
        if self._branches.get(branch) == parent_id:
            self._branches[branch] = node.id
        if self.tip_id == parent_id and self._position_version == version:
            self._branches[self._active_branch] = node.id
            await self.refresh_from_entry(entry)
        return entry

    async def pending_files(self, node_id: str | None = None) -> tuple[StagedFile, ...]:
        await self.ensure_ready()
        node_id = self.tip_id if node_id is None else node_id
        pending = {}
        seen = set()
        cursor = None
        while True:
            page = await self.store.list_history(
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

    async def spawn(
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
    ) -> AsyncOperationContract:
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
        return await self.spawn_request(request)

    def create_operation_record(self, operation: AsyncOperationContract) -> OperationRecord:
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

    async def detach(self, operation: AsyncOperationContract) -> OperationRecord:
        """Register an already spawned operation without reading events or closing it.

        Returns:
            Its durable record. The caller still owns the live handle.

        Raises:
            ValueError: The operation does not belong to this session.

        """
        context = operation.context
        if context is None or context.session_id != self.session_id:
            raise ValueError("detach requires an operation spawned by this session")
        record = await self._register_operation(self.create_operation_record(operation))
        operation.context = replace(context, detached=True)
        return record

    async def spawn_detached(self, command: str | None = None, **kwargs) -> OperationRecord:
        """Spawn and register a command; options are RunRequest fields.

        Returns:
            A durable record whose UUID can be passed to wait_operation.

        """
        operation = await self.spawn_request(RunRequest(command=command, **kwargs))
        try:
            return await self.detach(operation)
        except BaseException:
            with suppress(Exception):
                await operation.cancel()
            raise

    async def restore_operation(self, operation_uuid: str) -> AsyncOperationContract:
        """Recreate a control handle from the persisted source context.

        Returns:
            An unentered handle. Use wait_operation to reuse a stored final result.

        """
        await self.ensure_ready()
        record = await self.get_operation(operation_uuid)
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

    async def list_operations(self, *, pending_only: bool = True) -> tuple[OperationRecord, ...]:
        await self.ensure_ready()
        records = []
        cursor = None
        while True:
            page = await self.store.list_nodes(
                self.session_id, kind="operation-pending", limit=MAX_NODE_BATCH_SIZE, cursor=cursor
            )
            pending = [
                OperationRecord.from_dict(cast("dict[str, JSONValue]", node.data["record"])) for node in page.items
            ]
            completed = (
                await self.store.get_nodes(self.session_id, tuple(record.node_id for record in pending))
                if pending
                else ()
            )
            for record, node in zip(pending, completed, strict=True):
                if node is not None:
                    record = OperationRecord.from_dict(cast("dict[str, JSONValue]", node.data["record"]))
                if not pending_only or record.pending:
                    records.append(record)
            cursor = page.next_cursor
            if cursor is None:
                return tuple(sorted(records, key=lambda record: record.uuid))

    async def _finish_detached(self, operation: AsyncOperationContract) -> OperationRecord:
        await self.ensure_ready()
        record = await self.get_operation(operation.uuid)
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
            await self.store.append(self.session_id, node)
        except NodeConflictError:
            return await self.get_operation(record.uuid)
        return completed

    async def wait_operation(
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
        await self.ensure_ready()
        version = self._position_version
        record = await self.get_operation(operation_uuid)
        self.check_operation_endpoint(record)
        was_pending = record.pending
        if record.pending:
            operation = await self.restore_operation(operation_uuid)
            async with owned_async_operation(operation):
                try:
                    await operation.wait(timeout=timeout)
                except BaseException as error:
                    response = operation.response
                    if response is not None and response.status in {OperationStatus.FAILED, OperationStatus.CANCELLED}:
                        try:
                            await self._finish_detached(operation)
                        except Exception as save_error:
                            raise error from save_error
                    raise
            record = await self._finish_detached(operation)
        if branch is not None and record.history_id is not None:
            self._branches[branch] = record.history_id
        if was_pending and record.history_id is not None:
            entry = await self.get_entry(record.history_id)
            if self._branches.get(record.branch) == record.parent_id:
                self._branches[record.branch] = entry.id
            if (
                self.tip_id == record.parent_id
                and self._active_branch == record.branch
                and self._position_version == version
            ):
                await self.refresh_from_entry(entry)
        return instance_result(decode_response(record))

    async def commit_result(
        self,
        operation: AsyncOperationContract,
        *,
        title: str | None = None,
        branch: str | None = None,
        files: tuple[str, ...] | None = None,
        data: dict[str, JSONValue] | None = None,
    ) -> HistoryEntry | None:
        await self.ensure_ready()
        context = operation.context
        if context is None or context.session_id != self.session_id:
            raise ValueError("operation does not belong to this session")
        if context.detached:
            if files is not None or (title is not None and title != context.request.title):
                raise ValueError("detached metadata is fixed at registration")
            record = await self._finish_detached(operation)
            instance_result(decode_response(record))
            if record.history_id is None:
                return None
            entry = await self.get_entry(record.history_id)
            if self._branches.get(record.branch) == record.parent_id:
                self._branches[record.branch] = entry.id
            if (
                self.tip_id == record.parent_id
                and self._active_branch == record.branch
                and self._position_version == context.position_version
            ):
                await self.refresh_from_entry(entry)
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
        await self.store.append(self.session_id, node)
        entry = entry_from_node(self.session_id, node)
        if context.branch is not None and self._branches.get(context.branch) == context.parent_id:
            self._branches[context.branch] = node.id
        if branch is not None:
            self._branches[branch] = node.id
            self._active_branch = branch
            await self.refresh_from_entry(entry)
        elif (
            self.tip_id == context.parent_id
            and self._active_branch == context.branch
            and (self._position_version == context.position_version)
        ):
            self._branches[self._active_branch] = node.id
            await self.refresh_from_entry(entry)
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
    ) -> PendingRun:
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
        return self.create_pending_run(request, branch=branch)

    async def refresh_from_entry(self, entry: HistoryEntry) -> None:
        self.tip_id = entry.id
        self.image_uuid = entry.image_uuid

    async def create_branch(self, name: str, *, from_branch: str | None = None) -> None:
        await self.ensure_ready()
        if not name or name in self._branches:
            raise ValueError("branch name is empty or already exists")
        if from_branch is not None and from_branch not in self._branches:
            raise ValueError("unknown source branch")
        self._branches[name] = self._branches[from_branch] if from_branch else self.tip_id

    async def switch_branch(self, name: str) -> None:
        await self.ensure_ready()
        if name not in self._branches:
            raise ValueError("unknown local branch")
        entry = await self.get_entry(self._branches[name])
        self._active_branch = name
        self._position_version += 1
        await self.refresh_from_entry(entry)

    async def list_branches(self) -> list[tuple[str, bool]]:
        await self.ensure_ready()
        return [(name, name == self._active_branch) for name in sorted(self._branches)]

    async def delete_branch(self, name: str) -> None:
        await self.ensure_ready()
        if name == self._active_branch:
            raise ValueError("cannot delete the selected local branch")
        if name not in self._branches:
            raise ValueError("unknown local branch")
        del self._branches[name]

    async def rollback(self, steps: int = 1) -> None:
        await self.ensure_ready()
        if steps < 0:
            raise ValueError("steps must be nonnegative")
        node = await self.store.get_node(self.session_id, self.tip_id)
        for _ in range(steps):
            if node.parent_id is None:
                raise ValueError("cannot roll back beyond the root")
            node = await self.store.get_node(self.session_id, node.parent_id)
        await self.navigate(node.id)

    async def navigate(self, node_id: str) -> None:
        await self.ensure_ready()
        entry = await self.get_entry(node_id)
        self._position_version += 1
        self._branches[self._active_branch] = entry.id
        await self.refresh_from_entry(entry)

    async def navigate_forward(self, steps: int = 1) -> None:
        await self.ensure_ready()
        if steps < 0:
            raise ValueError("steps must be nonnegative")
        node_id = self.tip_id
        for _ in range(steps):
            children = []
            cursor = None
            while True:
                page = await self.store.list_children(self.session_id, node_id, cursor=cursor)
                children.extend(node for node in page.items if node.data.get("image_uuid"))
                cursor = page.next_cursor
                if cursor is None:
                    break
            if len(children) != 1:
                raise ValueError("forward requires exactly one continuation; navigate to an explicit node")
            node_id = children[0].id
        await self.navigate(node_id)

    async def history(self) -> tuple[list[HistoryEntry], dict[str, list[str]]]:
        await self.ensure_ready()
        entries = [
            entry_from_node(self.session_id, node)
            for node in await self._all_nodes()
            if node.data.get("image_uuid") and node.kind != "operation-pending"
        ]
        names = {}
        for name, node_id in self._branches.items():
            names.setdefault(node_id, []).append(name)
        return (order_entries(entries), names)

    def create_store(self) -> AsyncStore:  # noqa: PLR6301 - public extension contract
        """Create the default store when none was supplied.

        Returns:
            A new memory store owned by this session.

        """
        return AsyncMemoryStore()

    def create_file_transfer(self) -> AsyncFileTransfer:
        """Create file I/O when no component was supplied.

        Returns:
            A file-transfer component using the session client.

        """
        return AsyncClientFileTransfer(self.client)

    async def resolve_image(self, image: str) -> str:
        """Resolve a base image. Override to implement an import or registry policy.

        Returns:
            The resolved image UUID.

        """
        return await self.client.resolve_image(image)

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

    def create_inspector(self, image_uuid: str) -> AsyncImageInspector:
        """Create a view of one image. Override to customize inspection.

        Returns:
            An inspector borrowing the client's connection and file transfer.

        """
        return AsyncImageInspector(self.client, image_uuid, self.file_transfer)

    async def inspect(self) -> AsyncImageInspector:
        """Pin the current saved image without starting a VM.

        Pending staged attachments appear only after an operation applies them.

        Returns:
            A read-only view that borrows this session's client and file transfer.

        """
        await self.ensure_ready()
        image_uuid = require_str(self.image_uuid, "session has no resolved image")
        return self.create_inspector(image_uuid)

    async def list_dir(self, path: str = "/") -> DirectoryList:
        """List session directory entries relative to the filesystem root.

        Returns:
            Directory entries and their filesystem metadata.

        """
        view = await self.inspect()
        return await view.list(path)

    async def grep(
        self,
        pattern: str | Sequence[str],
        *,
        path: str | Sequence[str] | None = None,
        glob: str | Sequence[str] | None = None,
        max_count: int | None = None,
        max_total: int | None = None,
        case: Literal["sensitive", "insensitive", "smart"] | None = None,
        before: int | None = None,
        after: int | None = None,
    ) -> GrepResult:
        """Search session files using the current source's syntax and limits.

        Returns:
            Matching lines and the server's truncation indicator.

        """
        view = await self.inspect()
        return await view.grep(
            pattern,
            path=path,
            glob=glob,
            max_count=max_count,
            max_total=max_total,
            case=case,
            before=before,
            after=after,
        )

    async def read_file(self, path: str) -> bytes:
        view = await self.inspect()
        return await view.read_file(path)

    async def spawn_request(self, request: RunRequest) -> AsyncOperationContract:
        """Prepare and submit a command, then construct its operation through the factory.

        Returns:
            A bound operation whose context records the effective request.

        """
        await self.ensure_ready()
        request = self.prepare_request(request)
        image_uuid = require_str(self.image_uuid, "session has no resolved image")
        parent_id = self.tip_id
        position_version = self._position_version
        session_cwd, session_env = self.cwd, dict(self.env)
        branch = self._active_branch
        staged = await self.pending_files(parent_id)
        files = {item.path: item.as_spec() for item in staged}
        files.update(await self.file_transfer.prepare_files(request.files) or {})
        stdin = None
        if request.stdin is not None or request.stdin_open:
            data = await self.file_transfer.read_stdin(request.stdin) if request.stdin is not None else b""
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
        response = await self.submit_request(request, image_uuid, files=files or None, stdin=stdin)
        try:
            operation = self.create_operation(response, context)
            operation.context = context
        except BaseException:
            with suppress(Exception):
                await shield(self.client.cancel_operation(require_str(response.uuid, "missing operation uuid")))
            raise
        return operation

    async def submit_request(
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
        return await self.client.spawn_instance(
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

    def create_operation(self, response: InstanceSpawnResponse, context: OperationContext) -> AsyncOperationContract:
        """Construct a lifecycle implementation bound to the supplied operation context.

        Returns:
            An implementation of the matching operation lifecycle contract.

        """
        uuid = require_str(response.uuid, "spawn_instance response missing operation uuid")
        return AsyncOperation(self.client, uuid, timeout=context.request.timeout_seconds, context=context)

    async def execute(self, request: RunRequest, *, branch: str | None = None) -> InstanceResult:
        """Run a request to completion and commit its effective non-disposable result.

        Returns:
            The completed process result, including nonzero exit codes.

        """
        return await self.create_pending_run(request, branch=branch)

    def create_pending_run(self, request: RunRequest, *, branch: str | None = None) -> PendingRun:
        """Create the awaitable/context-manager wrapper for a command.

        Returns:
            A one-use wrapper for awaiting or entering the operation.

        """
        return PendingRun(self, request, branch=branch)

    async def _all_nodes(self, *, kind: str | None = None) -> list[Node]:
        result = []
        cursor = None
        while True:
            page = await self.store.list_nodes(self.session_id, kind=kind, cursor=cursor)
            result.extend(page.items)
            cursor = page.next_cursor
            if cursor is None:
                return result

    async def _initialize(self, image: str | None, node_id: str | None, tree_kind: str) -> None:
        info = await self.store.get_session(self.session_id)
        if info is None:
            if image is None:
                raise ValueError("unknown session; provide an image to create it")
            await self.store.create_session(self.session_id, kind=tree_kind)
        roots = (await self.store.list_children(self.session_id, None)).items
        if not roots:
            if image is None:
                raise ValueError("session has no root image")
            root = entry_node(
                parent_id=None,
                image_uuid=await self.resolve_image(image),
                kind="init",
                created_at=time.time(),
                cwd=self.cwd,
                env=self.env,
            )
            try:
                await self.store.append(self.session_id, root)
            except NodeConflictError:
                roots = (await self.store.list_children(self.session_id, None)).items
                if not roots:
                    raise
        if node_id is None:
            nodes = await self._all_nodes()
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
            node = await self.store.get_node(self.session_id, node_id)
        await self.refresh_from_entry(entry_from_node(self.session_id, node))
        if self.cwd_override is None:
            self.cwd = cast("str | None", node.data.get("cwd"))
        if self.env_override is None:
            self.env = dict(cast("dict[str, str]", node.data.get("env", {})))
        self._branches = {"main": self.tip_id}

    async def get_entry(self, node_id: str) -> HistoryEntry:
        await self.ensure_ready()
        return entry_from_node(self.session_id, await self.store.get_node(self.session_id, node_id))

    async def get_operation(self, operation_uuid: str) -> OperationRecord:
        pending = await self.store.get_node(self.session_id, "operation-pending:" + operation_uuid)
        record = OperationRecord.from_dict(cast("dict[str, JSONValue]", pending.data["record"]))
        try:
            completed = await self.store.get_node(self.session_id, record.node_id)
        except ValueError:
            return record
        return OperationRecord.from_dict(cast("dict[str, JSONValue]", completed.data["record"]))

    async def _register_operation(self, record: OperationRecord) -> OperationRecord:
        await self.ensure_ready()
        node = Node(
            id="operation-pending:" + record.uuid,
            parent_id=record.parent_id,
            kind="operation-pending",
            data={"record": record.to_dict(), "operation_uuid": record.uuid},
        )
        await self.store.append(self.session_id, node)
        return await self.get_operation(record.uuid)

    async def _save_configuration(self) -> None:
        node = entry_node(
            parent_id=self.tip_id,
            image_uuid=self.image_uuid,
            kind="config",
            created_at=time.time(),
            cwd=self.cwd,
            env=self.env,
        )
        await self.store.append(self.session_id, node)
        self._branches[self._active_branch] = node.id
        self._position_version += 1
        await self.refresh_from_entry(entry_from_node(self.session_id, node))
