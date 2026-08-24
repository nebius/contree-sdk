from __future__ import annotations

from asyncio import Lock, gather, to_thread
from collections.abc import Iterable
from datetime import timedelta
from math import ceil
from pathlib import Path
from typing import TYPE_CHECKING

from contree_client.models import OperationStatus

from contree_sdk._internals.io.typing import INPUT_TYPES
from contree_sdk._internals.io.wiring import read_input
from contree_sdk.session.base import (
    RunFiles,
    exit_code_of,
    file_spec_for,
    instance_result,
    new_session_id,
    require_str,
    stream_repr_for_stdin,
    validate_command,
)
from contree_sdk.session.operation_async import AsyncOperation
from contree_sdk.store import AsyncMemoryStore, AsyncStore, HistoryEntry
from contree_sdk.utils.models.file import UploadedFile, UploadFileSpec


if TYPE_CHECKING:
    from contree_client.models import FileSpec, InstanceResult
    from contree_client.types import ContreeAsyncClient


class PendingRun:
    """Returned by `ContreeAsyncSession.run()`.

    Both awaitable (spawns, waits for the whole operation, commits to history if
    not disposable - identical to the pre-Operation-API `run()` behavior) and an
    async context manager (spawns without waiting, starts the background event
    consumer, yields the `AsyncOperation`) - the same dual shape as aiohttp's
    `session.get(url)`.
    """

    def __init__(
        self,
        session: ContreeAsyncSession,
        *,
        command: str | None,
        shell: str | None,
        args: Iterable[str],
        env: dict[str, str] | None,
        cwd: str | None,
        stdin: INPUT_TYPES | None,
        files: RunFiles,
        timeout: float | timedelta | None,
        disposable: bool,
        truncate_output_at: int | None,
        preserve_env: bool,
        hostname: str | None,
        branch: str | None,
    ) -> None:
        self.session = session
        self.command = command
        self.shell = shell
        self.args = args
        self.env = env
        self.cwd = cwd
        self.stdin = stdin
        self.files = files
        self.timeout = timeout
        self.disposable = disposable
        self.truncate_output_at = truncate_output_at
        self.preserve_env = preserve_env
        self.hostname = hostname
        self.branch = branch
        self.operation: AsyncOperation | None = None

    async def spawn(self) -> AsyncOperation:
        operation = await self.session.spawn(
            self.command,
            shell=self.shell,
            args=self.args,
            env=self.env,
            cwd=self.cwd,
            stdin=self.stdin,
            files=self.files,
            timeout=self.timeout,
            disposable=self.disposable,
            truncate_output_at=self.truncate_output_at,
            preserve_env=self.preserve_env,
            hostname=self.hostname,
        )
        self.operation = operation
        return operation

    def __await__(self):
        return self.run_to_result().__await__()

    async def run_to_result(self) -> InstanceResult:
        resolved_command = validate_command(self.command, self.shell)
        operation = await self.spawn()
        result = await operation.wait()
        if not self.disposable:
            await self.session.commit_result(operation, title=resolved_command, branch=self.branch)
        return result

    async def __aenter__(self) -> AsyncOperation:
        operation = await self.spawn()
        await operation.__aenter__()
        return operation

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        operation = self.operation
        if operation is None:
            return
        await operation.__aexit__(exc_type, exc, tb)
        if not self.disposable and exc_type is None:
            response = await operation.status()
            if response.status == OperationStatus.SUCCESS:
                resolved_command = validate_command(self.command, self.shell)
                await self.session.commit_result(operation, title=resolved_command, branch=self.branch)


class ContreeAsyncSession:
    """A durable, resumable ConTree session backed by a Store."""

    def __init__(
        self,
        client: ContreeAsyncClient,
        *,
        image: str | None = None,
        session_id: str | None = None,
        store: AsyncStore | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        if image is None and session_id is None:
            raise ValueError("either image or session_id must be provided")
        self.client = client
        self.store = store or AsyncMemoryStore()
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
                resolved = await self.client.resolve_image(self.image)
                entry = await self.store.append(self.session_id, image_uuid=resolved, parent_id=None, kind="init")
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
        for key, value in updates.items():
            if value is None:
                self.env.pop(key, None)
            else:
                self.env[key] = value
        self.env_override = self.env
        await self.store.set_session_env(self.session_id, updates)

    async def upload_file(self, file: UploadFileSpec) -> FileSpec:
        source = file.source
        if isinstance(source, UploadedFile):
            uploaded = source
        else:
            path = Path(source) if isinstance(source, str) else source
            content = await to_thread(path.read_bytes) if isinstance(path, Path) else path
            response = await self.client.ensure_file(content)
            uploaded = UploadedFile(uuid=response.uuid, sha256=response.sha256)
        return file_spec_for(uploaded, file)

    async def build_files(self, files: RunFiles) -> dict[str, FileSpec] | None:
        prepared = UploadFileSpec.prepare_files(files or [])
        if not prepared:
            return None
        specs = await gather(*(self.upload_file(file) for file in prepared))
        return {str(file.path): spec for file, spec in zip(prepared, specs, strict=True)}

    async def spawn(
        self,
        command: str | None = None,
        *,
        shell: str | None = None,
        args: Iterable[str] = (),
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        stdin: INPUT_TYPES | None = None,
        files: RunFiles = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
        preserve_env: bool = False,
        hostname: str | None = None,
    ) -> AsyncOperation:
        # spawn command and return immediately with an AsyncOperation handle, without waiting
        resolved_command = validate_command(command, shell)
        await self.ensure_ready()
        image_uuid = require_str(self.image_uuid, "session has no resolved image")

        if isinstance(timeout, timedelta):
            timeout = timeout.total_seconds()

        file_specs = await self.build_files(files)
        stdin_repr = stream_repr_for_stdin(await read_input(stdin)) if stdin is not None else None

        response = await self.client.spawn_instance(
            resolved_command,
            image_uuid,
            disposable=disposable,
            shell=shell is not None,
            args=list(args),
            env=env if env is not None else (self.env if self.env else ...),
            cwd=cwd if cwd is not None else (self.cwd if self.cwd is not None else ...),
            preserve_env=preserve_env,
            hostname=hostname if hostname is not None else ...,
            timeout=ceil(timeout) if timeout is not None else ...,
            truncate_output_at=truncate_output_at if truncate_output_at is not None else ...,
            files=file_specs if file_specs is not None else ...,
            stdin=stdin_repr if stdin_repr is not None else ...,
        )
        operation_uuid = require_str(response.uuid, "spawn_instance response missing operation uuid")
        return AsyncOperation(
            self.client, operation_uuid, timeout=timeout, files=tuple(file_specs) if file_specs is not None else ()
        )

    async def commit_result(
        self,
        operation: AsyncOperation,
        *,
        title: str | None = None,
        branch: str | None = None,
        files: tuple[str, ...] | None = None,
    ) -> HistoryEntry:
        # append operation's result image to history - the "commit" step run() does inline;
        # files defaults to operation.files (already uploaded by spawn()), pass an explicit
        # tuple only to override that record
        response = operation.response
        if response is None:
            raise ValueError("operation has no response yet; call wait() or status() before commit_result()")
        result_image_uuid = require_str(response.result_image_uuid, "operation succeeded but reported no result image")
        result = instance_result(response)
        entry = await self.store.append(
            self.session_id,
            image_uuid=result_image_uuid,
            parent_id=self.tip_id,
            kind="run",
            title=title or "",
            operation_uuid=operation.uuid,
            exit_code=exit_code_of(result),
            branch=branch,
            files=files if files is not None else operation.files,
        )
        self.tip_id = entry.id
        self.image_uuid = entry.image_uuid
        return entry

    def run(
        self,
        command: str | None = None,
        *,
        shell: str | None = None,
        args: Iterable[str] = (),
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        stdin: INPUT_TYPES | None = None,
        files: RunFiles = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
        preserve_env: bool = False,
        hostname: str | None = None,
        branch: str | None = None,
    ) -> PendingRun:
        return PendingRun(
            self,
            command=command,
            shell=shell,
            args=args,
            env=env,
            cwd=cwd,
            stdin=stdin,
            files=files,
            timeout=timeout,
            disposable=disposable,
            truncate_output_at=truncate_output_at,
            preserve_env=preserve_env,
            hostname=hostname,
            branch=branch,
        )

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
