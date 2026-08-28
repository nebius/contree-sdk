from asyncio import Lock, gather
from pathlib import Path
from typing import overload
from uuid import uuid4

from contree_client.exceptions import NotFoundError, UnprocessableEntityError


try:
    from deepagents.backends.protocol import ExecuteResponse, FileDownloadResponse, FileUploadResponse
    from deepagents.backends.sandbox import BaseSandbox
except ImportError as e:
    raise ImportError(
        'contree_sdk.langchain needs the "langchain" extra (deepagents, Python >= 3.11): '
        'install with `pip install "contree-sdk[langchain]"`.'
    ) from e

from contree_sdk.sdk.objects.image_like.result import ContreeResult
from contree_sdk.sdk.objects.session import ContreeSession, ContreeSessionSync
from contree_sdk.utils.models.file import UploadFileSpec


def to_execute_response(result: ContreeResult) -> ExecuteResponse:
    truncated = bool(result.truncated)
    output = ""
    for part in (result.stdout, result.stderr):
        if part is None:
            continue
        output += str(part)
    return ExecuteResponse(output=output, exit_code=result.exit_code, truncated=truncated)


class BaseContreeSandbox(BaseSandbox):
    """Shared state for `ContreeSandboxAsync`/`ContreeSandboxSync`.

    Each concrete subclass only implements the methods matching its own
    session's transport; calling the other direction raises
    `NotImplementedError` instead of silently bridging across threads or an
    event loop. Build one via the `ContreeSandbox(session)` factory function
    below, which picks the right subclass for the session you pass it.
    """

    session: ContreeSession | ContreeSessionSync

    def __init__(self, session: ContreeSession | ContreeSessionSync):
        self.session = session
        self.sandbox_id = f"contree-{uuid4()}-from-{session.uuid}"

    @property
    def id(self) -> str:
        return self.sandbox_id


class ContreeSandboxAsync(BaseContreeSandbox):
    session: ContreeSession

    def __init__(self, session: ContreeSession):
        super().__init__(session)
        self.lock = Lock()

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        valid: dict[str, str | Path | bytes | UploadFileSpec] = {
            path: data for path, data in files if path.startswith("/")
        }
        if valid:
            async with self.lock:
                await self.session.apply_files(valid)
        return [FileUploadResponse(path=path, error=None if path in valid else "invalid_path") for path, *_ in files]

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        raise NotImplementedError("ContreeSandbox wraps an async session here; use aupload_files()")

    async def download_one_file(self, path: str) -> FileDownloadResponse:
        if not path.startswith("/"):
            return FileDownloadResponse(path=path, error="invalid_path")
        try:
            content = await self.session.read(path)
            return FileDownloadResponse(path=path, content=content)
        except NotFoundError:
            return FileDownloadResponse(path=path, error="file_not_found")
        except UnprocessableEntityError:
            return FileDownloadResponse(path=path, error="invalid_path")

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        async with self.lock:
            return await gather(*(self.download_one_file(path) for path in paths))

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        raise NotImplementedError("ContreeSandbox wraps an async session here; use adownload_files()")

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        async with self.lock:
            result = (
                await self.session.run(
                    shell=command, timeout=timeout, disposable=False, truncate_output_at=10 * 1024 * 1024
                )
            ).result
        return to_execute_response(result)

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        raise NotImplementedError("ContreeSandbox wraps an async session here; use aexecute()")


class ContreeSandboxSync(BaseContreeSandbox):
    session: ContreeSessionSync

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        valid: dict[str, str | Path | bytes | UploadFileSpec] = {
            path: data for path, data in files if path.startswith("/")
        }
        if valid:
            self.session.apply_files(valid)
        return [FileUploadResponse(path=path, error=None if path in valid else "invalid_path") for path, *_ in files]

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        raise NotImplementedError("ContreeSandbox wraps a sync session here; use upload_files()")

    def download_one_file(self, path: str) -> FileDownloadResponse:
        if not path.startswith("/"):
            return FileDownloadResponse(path=path, error="invalid_path")
        try:
            content = self.session.read(path)
            return FileDownloadResponse(path=path, content=content)
        except NotFoundError:
            return FileDownloadResponse(path=path, error="file_not_found")
        except UnprocessableEntityError:
            return FileDownloadResponse(path=path, error="invalid_path")

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return [self.download_one_file(path) for path in paths]

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        raise NotImplementedError("ContreeSandbox wraps a sync session here; use download_files()")

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        result = (
            self.session
            .run(shell=command, timeout=timeout, disposable=False, truncate_output_at=10 * 1024 * 1024)
            .wait()
            .result
        )
        return to_execute_response(result)

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        raise NotImplementedError("ContreeSandbox wraps a sync session here; use execute()")


@overload
def ContreeSandbox(session: ContreeSession) -> ContreeSandboxAsync: ...
@overload
def ContreeSandbox(session: ContreeSessionSync) -> ContreeSandboxSync: ...
def ContreeSandbox(  # noqa: N802
    session: ContreeSession | ContreeSessionSync,
) -> ContreeSandboxAsync | ContreeSandboxSync:
    """Build the `ContreeSandboxAsync`/`ContreeSandboxSync` matching `session`.

    Returns:
        A `ContreeSandboxAsync` for a `ContreeSession`, a `ContreeSandboxSync` for a `ContreeSessionSync`.

    """
    if isinstance(session, ContreeSession):
        return ContreeSandboxAsync(session)
    return ContreeSandboxSync(session)
