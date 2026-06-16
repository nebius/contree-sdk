from asyncio import gather
from uuid import uuid4

from deepagents.backends.protocol import ExecuteResponse, FileDownloadResponse, FileUploadResponse
from deepagents.backends.sandbox import BaseSandbox

from contree_sdk._internals.utils.wrapper import coro_sync
from contree_sdk.sdk.exceptions import NotFoundError, UnprocessableEntityError
from contree_sdk.sdk.objects.session import ContreeSession, ContreeSessionSync


class ContreeSandbox(BaseSandbox):
    def __init__(self, session: ContreeSession | ContreeSessionSync):
        self._session = session
        self._id = f"contree-{uuid4()}-from-{self._session.uuid}"

    @property
    def id(self) -> str:
        return self._id

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        uploaded_files = await gather(*(self._session.client.files._upload_bytes_file(file[1]) for file in files))
        mapped_files = {}
        for (path, *_), uploaded_file in zip(files, uploaded_files, strict=True):
            if not path.startswith("/"):
                continue

            mapped_files[path] = uploaded_file
        await ContreeSession.apply_files(self._session, mapped_files)
        return [
            FileUploadResponse(path=path, error=None if path in mapped_files else "invalid_path") for path, *_ in files
        ]

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return coro_sync(self.aupload_files(files))

    async def _adownload_file(self, path: str) -> FileDownloadResponse:
        if not path.startswith("/"):
            return FileDownloadResponse(path=path, error="invalid_path")
        try:
            content = await self._session._read_file(path)
            return FileDownloadResponse(path=path, content=content)
        except NotFoundError:
            return FileDownloadResponse(path=path, error="file_not_found")
        except UnprocessableEntityError:
            return FileDownloadResponse(path=path, error="invalid_path")

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return await gather(*(self._adownload_file(path) for path in paths))

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return coro_sync(self.adownload_files(paths))

    async def aexecute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:

        result = (
            await self._session.run(
                shell=command, timeout=timeout, disposable=False, truncate_output_at=10 * 1024 * 1024
            )._await()
        ).result
        truncated = False
        if result._raw is not None and result._raw.result is not None:
            truncated = result._raw.result.stdout.truncated or result._raw.result.stderr.truncated
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
