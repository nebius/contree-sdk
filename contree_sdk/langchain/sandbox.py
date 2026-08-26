from asyncio import Lock, gather, run
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, TypeVar
from uuid import uuid4

from contree_client.exceptions import NotFoundError, UnprocessableEntityError
from deepagents.backends.protocol import ExecuteResponse, FileDownloadResponse, FileUploadResponse
from deepagents.backends.sandbox import BaseSandbox

from contree_sdk.sdk.objects.session import ContreeSession, ContreeSessionSync


T = TypeVar("T")


def coro_sync(coro: Coroutine[Any, Any, T]) -> T:
    return run(coro)


class ContreeSandbox(BaseSandbox):
    def __init__(self, session: ContreeSession | ContreeSessionSync):
        self._session = session if isinstance(session, ContreeSession) else ContreeSession(session)
        self._id = f"contree-{uuid4()}-from-{self._session.uuid}"
        self._lock = Lock()

    @property
    def id(self) -> str:
        return self._id

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        uploads = {path: data for path, data in files if path.startswith("/")}
        if uploads:
            uploaded = await gather(*(self._session.client.files._upload_bytes_file(data) for data in uploads.values()))
            async with self._lock:
                await self._session._apply_files(dict(zip(uploads, uploaded, strict=True)))
        return [FileUploadResponse(path=path, error=None if path in uploads else "invalid_path") for path, *_ in files]

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return coro_sync(self.aupload_files(files))

    async def _adownload_file(self, path: str) -> FileDownloadResponse:
        if not path.startswith("/"):
            return FileDownloadResponse(path=path, error="invalid_path")
        try:
            content = await self._session.read(path)
            return FileDownloadResponse(path=path, content=content)
        except NotFoundError:
            return FileDownloadResponse(path=path, error="file_not_found")
        except UnprocessableEntityError:
            return FileDownloadResponse(path=path, error="invalid_path")

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        async with self._lock:
            return await gather(*(self._adownload_file(path) for path in paths))

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return coro_sync(self.adownload_files(paths))

    async def aexecute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        async with self._lock:
            result = (
                await self._session.run(
                    shell=command, timeout=timeout, disposable=False, truncate_output_at=10 * 1024 * 1024
                )
            ).result
        truncated = bool(result.truncated)
        output = ""
        for part in (result.stdout, result.stderr):
            if part is None:
                continue
            output += str(part)
        return ExecuteResponse(
            output=output,
            exit_code=result.exit_code,
            truncated=truncated,
        )

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        return coro_sync(self.aexecute(command, timeout=timeout))
