"""Public file-transfer contracts and client-backed implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from asyncio import create_task, gather, to_thread
from collections.abc import AsyncGenerator, Generator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import aclosing, closing
from inspect import iscoroutinefunction
from pathlib import Path
from typing import Protocol, TypeAlias, TypeVar, cast

from contree_client.models import FileSpec
from contree_client.types import ContreeAsyncClient, ContreeSyncClient

from contree_sdk.file_io import (
    ProgressCallback,
    TransferProgress,
    hash_upload,
    run_file_io,
    write_download,
    write_download_async,
)
from contree_sdk.utils.models.file import UploadedFile, UploadFileSpec, prepare_file_tree


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

    max_concurrency = 1
    on_progress: ProgressCallback | None = None

    @abstractmethod
    def upload(self, file: UploadFileSpec) -> FileSpec: ...

    @abstractmethod
    def read_file(self, image_uuid: str, path: str) -> bytes: ...

    def prepare_files(self, files: RunFiles) -> dict[str, FileSpec] | None:
        prepared = UploadFileSpec.prepare_files(files or [])
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        if self.max_concurrency == 1:
            specs = [self.upload(file) for file in prepared]
        else:
            with ThreadPoolExecutor(max_workers=self.max_concurrency) as pool:
                futures = {pool.submit(self.upload, file): index for index, file in enumerate(prepared)}
                completed = {}
                try:
                    for future in as_completed(futures):
                        completed[futures[future]] = future.result()
                except BaseException:
                    for future in futures:
                        future.cancel()
                    raise
                specs = [completed[index] for index in range(len(prepared))]
        return {str(file.path): spec for file, spec in zip(prepared, specs, strict=True)} or None

    def iter_file(self, image_uuid: str, path: str) -> Generator[bytes, None, None]:
        """Yield file content. Override this buffered fallback for streaming backends.

        Yields:
            File content chunks. Close the generator if iteration stops early.

        """
        yield self.read_file(image_uuid, path)

    def download_file(self, image_uuid: str, path: str, destination: str | Path) -> int:
        """Atomically save streamed content.

        Returns:
            The number of downloaded bytes.

        """
        with closing(self.iter_file(image_uuid, path)) as chunks:
            return write_download(chunks, destination, path=path, on_progress=self.on_progress)

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

    prepare_files limits uploads to max_concurrency workers. It cancels and
    joins sibling uploads when one fails. Custom backends can replace batching.
    """

    max_concurrency = 4
    on_progress: ProgressCallback | None = None

    @abstractmethod
    async def upload(self, file: UploadFileSpec) -> FileSpec: ...

    @abstractmethod
    async def read_file(self, image_uuid: str, path: str) -> bytes: ...

    async def prepare_files(self, files: RunFiles) -> dict[str, FileSpec] | None:
        prepared = await run_file_io(UploadFileSpec.prepare_files, files or [])
        if not prepared:
            return None
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        pending = iter(prepared)
        specs: dict[str, FileSpec] = {}

        async def worker() -> None:
            for file in pending:
                specs[str(file.path)] = await self.upload(file)

        tasks = [create_task(worker()) for _ in range(min(self.max_concurrency, len(prepared)))]
        try:
            await gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await gather(*tasks, return_exceptions=True)
            raise
        return {str(file.path): specs[str(file.path)] for file in prepared}

    async def iter_file(self, image_uuid: str, path: str) -> AsyncGenerator[bytes, None]:
        """Yield file content. Override this buffered fallback for streaming backends.

        Yields:
            File content chunks. Close the generator if iteration stops early.

        """
        yield await self.read_file(image_uuid, path)

    async def download_file(self, image_uuid: str, path: str, destination: str | Path) -> int:
        """Atomically save streamed content.

        Returns:
            The number of downloaded bytes.

        """
        async with aclosing(self.iter_file(image_uuid, path)) as chunks:
            return await write_download_async(chunks, destination, path=path, on_progress=self.on_progress)

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

    def __init__(
        self, client: ContreeSyncClient, *, max_concurrency: int = 1, on_progress: ProgressCallback | None = None
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        self.client = client
        self.max_concurrency = max_concurrency
        self.on_progress = on_progress

    def upload(self, file: UploadFileSpec) -> FileSpec:
        source = file.source
        if isinstance(source, UploadedFile):
            uploaded = source
        else:
            path = Path(source) if isinstance(source, str) else source
            if isinstance(path, Path):
                with path.open("rb") as handle:
                    response = self.client.ensure_file(handle)
            else:
                response = self.client.ensure_file(path)
            uploaded = UploadedFile(uuid=response.uuid, sha256=response.sha256)
            if self.on_progress is not None:
                self.on_progress(TransferProgress("upload", str(file.path), response.size, response.size))
        return FileSpec(uuid=uploaded.uuid, uid=file.uid, gid=file.gid, mode=file.mode)

    def read_file(self, image_uuid: str, path: str) -> bytes:
        return self.client.inspect_image_download(image_uuid, path)

    def iter_file(self, image_uuid: str, path: str) -> Generator[bytes, None, None]:
        chunks = self.client.inspect_image_download_stream(image_uuid, path)
        try:
            yield from chunks
        finally:
            close = getattr(chunks, "close", None)
            if close is not None:
                close()


class AsyncClientFileTransfer(AsyncFileTransfer):
    """File transfer using a caller-owned asynchronous contree-client."""

    def __init__(
        self, client: ContreeAsyncClient, *, max_concurrency: int = 4, on_progress: ProgressCallback | None = None
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be positive")
        self.client = client
        self.max_concurrency = max_concurrency
        self.on_progress = on_progress

    async def upload(self, file: UploadFileSpec) -> FileSpec:
        source = file.source
        if isinstance(source, UploadedFile):
            uploaded = source
        else:
            path = Path(source) if isinstance(source, str) else source
            if isinstance(path, Path):
                with path.open("rb") as handle:
                    digest = await run_file_io(hash_upload, handle)
                    response = await self.client.ensure_file(handle, sha256=digest)
            else:
                response = await self.client.ensure_file(path)
            uploaded = UploadedFile(uuid=response.uuid, sha256=response.sha256)
            if self.on_progress is not None:
                self.on_progress(TransferProgress("upload", str(file.path), response.size, response.size))
        return FileSpec(uuid=uploaded.uuid, uid=file.uid, gid=file.gid, mode=file.mode)

    async def read_file(self, image_uuid: str, path: str) -> bytes:
        return await self.client.inspect_image_download(image_uuid, path)

    async def iter_file(self, image_uuid: str, path: str) -> AsyncGenerator[bytes, None]:
        async with aclosing(self.client.inspect_image_download_stream(image_uuid, path)) as chunks:
            async for chunk in chunks:
                yield chunk  # noqa: ASYNC119 - caller closes this generator; download_file uses aclosing


__all__ = [
    "AsyncClientFileTransfer",
    "AsyncFileTransfer",
    "AsyncReadable",
    "ClientFileTransfer",
    "InputSource",
    "Readable",
    "RunFiles",
    "SyncFileTransfer",
    "TransferProgress",
    "UploadFileSpec",
    "UploadedFile",
    "prepare_file_tree",
    "write_download",
    "write_download_async",
]
