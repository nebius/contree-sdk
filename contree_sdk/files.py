"""Public file-transfer contracts and client-backed implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from asyncio import create_task, gather, to_thread
from inspect import iscoroutinefunction
from pathlib import Path
from typing import Protocol, TypeAlias, TypeVar, cast

from contree_client.models import FileSpec
from contree_client.types import ContreeAsyncClient, ContreeSyncClient

from contree_sdk.utils.models.file import UploadedFile, UploadFileSpec


DataT_co = TypeVar("DataT_co", str, bytes, covariant=True)


class Readable(Protocol[DataT_co]):
    def read(self, size: int = -1, /) -> DataT_co: ...


class AsyncReadable(Protocol[DataT_co]):
    async def read(self, size: int = -1, /) -> DataT_co: ...


InputSource: TypeAlias = (
    str | bytes | Path | Readable[str] | Readable[bytes] | AsyncReadable[str] | AsyncReadable[bytes]
)
RunFiles: TypeAlias = list[str | Path | UploadFileSpec] | dict[str, str | Path | bytes | UploadFileSpec] | None


class SyncFileTransfer(ABC):
    """Replace upload, download, or stdin handling without replacing a session.

    Returned FileSpec values identify uploads on the same server as the session.
    Input streams belong to the caller and must not be closed by this component.
    """

    @abstractmethod
    def upload(self, file: UploadFileSpec) -> FileSpec: ...

    @abstractmethod
    def read_file(self, image_uuid: str, path: str) -> bytes: ...

    def prepare_files(self, files: RunFiles) -> dict[str, FileSpec] | None:
        prepared = UploadFileSpec.prepare_files(files or [])
        return {str(file.path): self.upload(file) for file in prepared} or None

    def read_stdin(self, source: InputSource) -> str | bytes:  # noqa: PLR6301 - public extension contract
        if isinstance(source, (str, bytes)):
            return source
        if isinstance(source, Path):
            return source.read_bytes()
        if iscoroutinefunction(source.read):
            raise TypeError("an async-readable stdin source requires an async session")
        return cast("str | bytes", source.read())


class AsyncFileTransfer(ABC):
    """Native async counterpart of SyncFileTransfer.

    prepare_files cancels and joins sibling uploads when an upload fails.
    Override it to add bounded concurrency or batching for a custom backend.
    """

    @abstractmethod
    async def upload(self, file: UploadFileSpec) -> FileSpec: ...

    @abstractmethod
    async def read_file(self, image_uuid: str, path: str) -> bytes: ...

    async def prepare_files(self, files: RunFiles) -> dict[str, FileSpec] | None:
        prepared = UploadFileSpec.prepare_files(files or [])
        if not prepared:
            return None
        tasks = [create_task(self.upload(file)) for file in prepared]
        try:
            specs = await gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await gather(*tasks, return_exceptions=True)
            raise
        return {str(file.path): spec for file, spec in zip(prepared, specs, strict=True)}

    async def read_stdin(self, source: InputSource) -> str | bytes:  # noqa: PLR6301 - public extension contract
        if isinstance(source, (str, bytes)):
            return source
        if isinstance(source, Path):
            return await to_thread(source.read_bytes)
        if iscoroutinefunction(source.read):
            return cast("str | bytes", await source.read())
        return cast("str | bytes", await to_thread(source.read))


class ClientFileTransfer(SyncFileTransfer):
    """File transfer using a caller-owned synchronous contree-client."""

    def __init__(self, client: ContreeSyncClient) -> None:
        self.client = client

    def upload(self, file: UploadFileSpec) -> FileSpec:
        source = file.source
        if isinstance(source, UploadedFile):
            uploaded = source
        else:
            path = Path(source) if isinstance(source, str) else source
            content = path.read_bytes() if isinstance(path, Path) else path
            response = self.client.ensure_file(content)
            uploaded = UploadedFile(uuid=response.uuid, sha256=response.sha256)
        return FileSpec(uuid=uploaded.uuid, uid=file.uid, gid=file.gid, mode=file.mode)

    def read_file(self, image_uuid: str, path: str) -> bytes:
        return self.client.inspect_image_download(image_uuid, path)


class AsyncClientFileTransfer(AsyncFileTransfer):
    """File transfer using a caller-owned asynchronous contree-client."""

    def __init__(self, client: ContreeAsyncClient) -> None:
        self.client = client

    async def upload(self, file: UploadFileSpec) -> FileSpec:
        source = file.source
        if isinstance(source, UploadedFile):
            uploaded = source
        else:
            path = Path(source) if isinstance(source, str) else source
            content = await to_thread(path.read_bytes) if isinstance(path, Path) else path
            response = await self.client.ensure_file(content)
            uploaded = UploadedFile(uuid=response.uuid, sha256=response.sha256)
        return FileSpec(uuid=uploaded.uuid, uid=file.uid, gid=file.gid, mode=file.mode)

    async def read_file(self, image_uuid: str, path: str) -> bytes:
        return await self.client.inspect_image_download(image_uuid, path)


__all__ = [
    "AsyncClientFileTransfer",
    "AsyncFileTransfer",
    "AsyncReadable",
    "ClientFileTransfer",
    "InputSource",
    "Readable",
    "RunFiles",
    "SyncFileTransfer",
    "UploadFileSpec",
    "UploadedFile",
]
