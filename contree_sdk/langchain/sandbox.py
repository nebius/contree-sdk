"""deepagents `BaseSandbox` backed by a ConTree session."""

from __future__ import annotations

import threading
from asyncio import Lock
from typing import Generic, TypeVar
from uuid import uuid4

from contree_client.exceptions import NotFoundError, UnprocessableEntityError
from contree_client.models import InstanceResult

from contree_sdk.execution import AsyncExecutor, RunRequest, SyncExecutor
from contree_sdk.files import RunFiles
from contree_sdk.session.base import or_none


try:
    from deepagents.backends.protocol import ExecuteResponse, FileDownloadResponse, FileUploadResponse
    from deepagents.backends.sandbox import BaseSandbox

    DEEPAGENTS_AVAILABLE = True
except ImportError:
    DEEPAGENTS_AVAILABLE = False

    class _MissingSandbox:
        pass

    BaseSandbox = _MissingSandbox  # ty: ignore[invalid-assignment]


def to_execute_response(result: InstanceResult) -> ExecuteResponse:
    stdout = or_none(result.stdout)
    stderr = or_none(result.stderr)
    state = or_none(result.state)
    output = (stdout.as_text() if stdout is not None else "") + (stderr.as_text() if stderr is not None else "")
    exit_code = or_none(state.exit_code) if state is not None else None
    truncated = bool(or_none(stdout.truncated) if stdout is not None else False) or bool(
        or_none(stderr.truncated) if stderr is not None else False
    )
    return ExecuteResponse(output=output, exit_code=exit_code, truncated=truncated)


SyncExecutorT = TypeVar("SyncExecutorT", bound=SyncExecutor)
AsyncExecutorT = TypeVar("AsyncExecutorT", bound=AsyncExecutor)


class ContreeSandbox(BaseSandbox, Generic[SyncExecutorT]):
    """A deepagents adapter for any SyncExecutor implementation.

    Mutating calls on this adapter are serialized. The executor remains
    caller-owned. deepagents may dispatch async calls through a thread pool;
    use ContreeAsyncSandbox for a native async executor.
    """

    def __init__(self, session: SyncExecutorT) -> None:
        if not DEEPAGENTS_AVAILABLE:
            raise ImportError(
                "ContreeSandbox requires the 'deepagents' package, which requires Python >= 3.11; "
                'install it via `pip install "contree-sdk[langchain]"` on Python >= 3.11'
            )
        self.session = session
        self.sandbox_id = f"contree-{session.session_id}-{uuid4().hex[:8]}"
        self.lock = threading.Lock()

    @property
    def id(self) -> str:
        return self.sandbox_id

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        with self.lock:
            result = self.session.execute(
                RunRequest(shell=command, timeout=timeout, disposable=False, truncate_output_at=10 * 1024 * 1024)
            )
        return to_execute_response(result)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        valid: RunFiles = {path: content for path, content in files if path.startswith("/")}
        if valid:
            with self.lock:
                self.session.execute(RunRequest(shell=":", files=valid, disposable=False))
        return [FileUploadResponse(path=path, error=None if path in valid else "invalid_path") for path, _ in files]

    def download_one_file(self, path: str) -> FileDownloadResponse:
        if not path.startswith("/"):
            return FileDownloadResponse(path=path, error="invalid_path")
        try:
            with self.lock:
                content = self.session.read_file(path)
            return FileDownloadResponse(path=path, content=content)
        except NotFoundError:
            return FileDownloadResponse(path=path, error="file_not_found")
        except UnprocessableEntityError:
            return FileDownloadResponse(path=path, error="invalid_path")

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return [self.download_one_file(path) for path in paths]


class ContreeAsyncSandbox(BaseSandbox, Generic[AsyncExecutorT]):
    """A deepagents sandbox with native asynchronous session operations."""

    def __init__(self, session: AsyncExecutorT) -> None:
        if not DEEPAGENTS_AVAILABLE:
            raise ImportError('ContreeAsyncSandbox requires `pip install "contree-sdk[langchain]"`')
        self.session = session
        self.sandbox_id = f"contree-{session.session_id}-{uuid4().hex[:8]}"
        self.lock = Lock()

    @property
    def id(self) -> str:
        return self.sandbox_id

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        raise NotImplementedError("Use aexecute() with ContreeAsyncSandbox")

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        raise NotImplementedError("Use aupload_files() with ContreeAsyncSandbox")

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        raise NotImplementedError("Use adownload_files() with ContreeAsyncSandbox")

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        async with self.lock:
            result = await self.session.execute(
                RunRequest(shell=command, timeout=timeout, disposable=False, truncate_output_at=10 * 1024 * 1024)
            )
        return to_execute_response(result)

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        valid: RunFiles = {path: content for path, content in files if path.startswith("/")}
        if valid:
            async with self.lock:
                await self.session.execute(RunRequest(shell=":", files=valid, disposable=False))
        return [FileUploadResponse(path=path, error=None if path in valid else "invalid_path") for path, _ in files]

    async def download_one_file(self, path: str) -> FileDownloadResponse:
        if not path.startswith("/"):
            return FileDownloadResponse(path=path, error="invalid_path")
        try:
            async with self.lock:
                content = await self.session.read_file(path)
            return FileDownloadResponse(path=path, content=content)
        except NotFoundError:
            return FileDownloadResponse(path=path, error="file_not_found")
        except UnprocessableEntityError:
            return FileDownloadResponse(path=path, error="invalid_path")

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return [await self.download_one_file(path) for path in paths]
