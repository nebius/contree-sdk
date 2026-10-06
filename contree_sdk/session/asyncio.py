from __future__ import annotations

from asyncio import Lock, shield
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import replace
from datetime import timedelta
from math import ceil

from contree_client.models import ClosableStreamRepr, FileSpec, InstanceResult, InstanceSpawnResponse, OperationStatus
from contree_client.types import ContreeAsyncClient

from contree_sdk.exceptions import SessionConflictError
from contree_sdk.execution import AsyncExecutor, OperationContext, RunRequest
from contree_sdk.files import AsyncClientFileTransfer, AsyncFileTransfer, InputSource, RunFiles, UploadFileSpec
from contree_sdk.session.base import exit_code_of, instance_result, new_session_id, require_str, stream_repr_for_stdin
from contree_sdk.session.contracts import AsyncOperationContract
from contree_sdk.session.operation_async import AsyncOperation
from contree_sdk.store import AsyncMemoryStore, AsyncStore, HistoryEntry


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
        store: AsyncStore | None = None,
        file_transfer: AsyncFileTransfer | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        if image is None and session_id is None:
            raise ValueError("either image or session_id must be provided")
        self.client = client
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
        self.tip_id: int | None = None
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
            if self.cwd_override is None or self.env_override is None:
                metadata = await self.store.get_session_metadata(self.session_id)
                if self.cwd_override is None:
                    self.cwd = metadata.cwd
                if self.env_override is None:
                    self.env = dict(metadata.env)
            tip = await self.store.tip(self.session_id)
            if tip is not None:
                self.image_uuid = tip.image_uuid
                self.tip_id = tip.id
            elif self.image is not None:
                resolved = await self.resolve_image(self.image)
                try:
                    entry = await self.store.append(
                        self.session_id, image_uuid=resolved, parent_id=None, kind="init", expected_tip=None
                    )
                except SessionConflictError:
                    entry = await self.store.tip(self.session_id)
                    if entry is None:
                        raise
                self.image_uuid = entry.image_uuid
                self.tip_id = entry.id
            else:
                raise ValueError(f"session {self.session_id!r} has no history and no image was given")
            self.ready = True

    async def set_cwd(self, cwd: str | None) -> None:
        self.cwd = cwd
        self.cwd_override = cwd
        await self.store.set_session_cwd(self.session_id, cwd)

    async def set_env(self, updates: dict[str, str | None]) -> None:
        await self.ensure_ready()
        for key, value in updates.items():
            if value is None:
                self.env.pop(key, None)
            else:
                self.env[key] = value
        self.env_override = self.env
        await self.store.set_session_env(self.session_id, updates)

    async def upload_file(self, file: UploadFileSpec) -> FileSpec:
        return await self.file_transfer.upload(file)

    async def build_files(self, files: RunFiles) -> dict[str, FileSpec] | None:
        return await self.file_transfer.prepare_files(files)

    async def spawn(
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
    ) -> AsyncOperationContract:
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
        return await self.spawn_request(request)

    async def commit_result(
        self,
        operation: AsyncOperationContract,
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
        entry = await self.store.append(
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
            await self.store.switch_branch(self.session_id, branch)
            if branch is not None
            else await self.store.tip(self.session_id)
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
    ) -> PendingRun:
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
        return self.create_pending_run(request, branch=branch)

    async def refresh_from_entry(self, entry: HistoryEntry) -> None:
        self.tip_id = entry.id
        self.image_uuid = entry.image_uuid

    async def create_branch(self, name: str, *, from_branch: str | None = None) -> None:
        await self.ensure_ready()
        await self.store.create_branch(self.session_id, name, from_branch=from_branch)

    async def switch_branch(self, name: str) -> None:
        await self.ensure_ready()
        entry = await self.store.switch_branch(self.session_id, name)
        await self.refresh_from_entry(entry)

    async def list_branches(self) -> list[tuple[str, bool]]:
        await self.ensure_ready()
        return await self.store.list_branches(self.session_id)

    async def delete_branch(self, name: str) -> None:
        await self.ensure_ready()
        await self.store.delete_branch(self.session_id, name)

    async def rollback(self, steps: int = 1) -> None:
        await self.ensure_ready()
        entry = await self.store.rollback(self.session_id, steps)
        await self.refresh_from_entry(entry)

    async def navigate(self, target: int) -> None:
        await self.ensure_ready()
        entry = await self.store.navigate(self.session_id, target)
        await self.refresh_from_entry(entry)

    async def navigate_forward(self, steps: int = 1) -> None:
        await self.ensure_ready()
        entry = await self.store.navigate_forward(self.session_id, steps)
        await self.refresh_from_entry(entry)

    async def history(self) -> tuple[list[HistoryEntry], dict[int, list[str]]]:
        await self.ensure_ready()
        return await self.store.history_dag(self.session_id)

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

    async def read_file(self, path: str) -> bytes:
        await self.ensure_ready()
        image_uuid = require_str(self.image_uuid, "session has no resolved image")
        return await self.file_transfer.read_file(image_uuid, path)

    async def spawn_request(self, request: RunRequest) -> AsyncOperationContract:
        """Prepare and submit a command, then construct its operation through the factory.

        Returns:
            A bound operation whose context records the effective request.

        """
        await self.ensure_ready()
        request = self.prepare_request(request)
        image_uuid = require_str(self.image_uuid, "session has no resolved image")
        parent_id = self.tip_id
        branch = await self.store.active_branch(self.session_id)
        files = await self.build_files(request.files)
        stdin = (
            stream_repr_for_stdin(await self.file_transfer.read_stdin(request.stdin))
            if request.stdin is not None
            else None
        )
        context = OperationContext(request, self.session_id, image_uuid, parent_id, branch, tuple(files or ()))
        response = await self.submit_request(request, image_uuid, files=files, stdin=stdin)
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
