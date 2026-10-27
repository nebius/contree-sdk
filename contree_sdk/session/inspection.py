"""Inspection views that select the session's current filesystem per request."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Callable, Generator, Iterator, Sequence
from contextlib import AbstractAsyncContextManager, AbstractContextManager, aclosing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from contree_client.models import DirectoryList, GrepResult, Image
from contree_client.types import ContreeAsyncClient, ContreeSyncClient

from contree_sdk.file_io import ProgressCallback, write_download, write_download_async
from contree_sdk.inspection import AsyncImageInspector, ImageInspector


@contextmanager
def _stream(chunks: Iterator[bytes]) -> Iterator[Iterator[bytes]]:
    try:
        yield chunks
    finally:
        close = getattr(chunks, "close", None)
        if close is not None:
            close()


@dataclass(frozen=True)
class SessionInspector:
    """Read current session files, reserving a live VM for each complete request.

    source yields either a pinned image inspector or a reserved operation UUID.
    Streams reserve their source on first iteration and release it on close.
    Paths are relative to the filesystem root, not the command's cwd.
    """

    client: ContreeSyncClient
    source: Callable[[], AbstractContextManager[ImageInspector | str]]
    saved_image: Callable[[], ImageInspector]
    on_progress: ProgressCallback | None = None

    def info(self) -> Image:
        """Save active work and return image metadata. This explicitly stops the VM.

        Returns:
            Metadata for the saved image.

        """
        return self.saved_image().info()

    def list(self, path: str = "/") -> DirectoryList:
        with self.source() as source:
            if isinstance(source, ImageInspector):
                return source.list(path)
            return self.client.inspect_instance_list(source, path)

    def grep(
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
        """Search the current source using its server-defined syntax and limits.

        Live grep and image grep have different regex and encoding support.
        Unsupported live patterns raise; there is no snapshot fallback.

        Returns:
            Matches and the server's truncation indicator.

        """
        with self.source() as source:
            if isinstance(source, ImageInspector):
                return source.grep(
                    pattern,
                    path=path,
                    glob=glob,
                    max_count=max_count,
                    max_total=max_total,
                    case=case,
                    before=before,
                    after=after,
                )
            return self.client.inspect_instance_grep(
                source,
                pattern,
                path=path,
                glob=glob,
                max_count=max_count,
                max_total=max_total,
                case=case,
                before=before,
                after=after,
            )

    def read_file(self, path: str) -> bytes:
        with self.source() as source:
            if isinstance(source, ImageInspector):
                return source.read_file(path)
            return self.client.inspect_instance_download(source, path)

    def download_file(self, path: str, destination: str | Path) -> int:
        """Download atomically; leave destination unchanged if the transfer fails.

        Returns:
            The number of downloaded bytes.

        """
        with self.source() as source:
            if isinstance(source, ImageInspector):
                return source.download_file(path, destination)
            with _stream(self.client.inspect_instance_download_stream(source, path)) as chunks:
                return write_download(chunks, destination, path=path, on_progress=self.on_progress)

    def file_exists(self, path: str) -> bool:
        with self.source() as source:
            if isinstance(source, ImageInspector):
                return source.file_exists(path)
            return self.client.check_instance_file(source, path)

    def archive_exists(self, path: str) -> bool:
        with self.source() as source:
            if isinstance(source, ImageInspector):
                return source.archive_exists(path)
            return self.client.check_instance_archive(source, path)

    def iter_file(self, path: str) -> Generator[bytes, None, None]:
        """Stream one source. Close the generator if iteration stops early.

        Yields:
            File content chunks while the source remains reserved.

        """
        with self.source() as source:
            chunks = (
                source.iter_file(path)
                if isinstance(source, ImageInspector)
                else self.client.inspect_instance_download_stream(source, path)
            )
            with _stream(chunks):
                yield from chunks

    def archive(self, path: str, *, compressed: bool = False) -> Generator[bytes, None, None]:
        """Stream tar content. Close the generator if iteration stops early.

        Yields:
            Archive chunks; compressed=True retains server compression.

        """
        with self.source() as source:
            chunks = (
                source.archive(path, compressed=compressed)
                if isinstance(source, ImageInspector)
                else self.client.inspect_instance_archive(source, path, compressed=compressed)
            )
            with _stream(chunks):
                yield from chunks


@dataclass(frozen=True)
class AsyncSessionInspector:
    """Native async view of current session files, reserved for each request."""

    client: ContreeAsyncClient
    source: Callable[[], AbstractAsyncContextManager[AsyncImageInspector | str]]
    saved_image: Callable[[], Awaitable[AsyncImageInspector]]
    on_progress: ProgressCallback | None = None

    async def info(self) -> Image:
        """Save active work and return image metadata. This explicitly stops the VM.

        Returns:
            Metadata for the saved image.

        """
        view = await self.saved_image()
        return await view.info()

    async def list(self, path: str = "/") -> DirectoryList:
        async with self.source() as source:
            if isinstance(source, AsyncImageInspector):
                return await source.list(path)
            return await self.client.inspect_instance_list(source, path)

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
        """Search the current source using its server-defined syntax and limits.

        Live grep and image grep have different regex and encoding support.
        Unsupported live patterns raise; there is no snapshot fallback.

        Returns:
            Matches and the server's truncation indicator.

        """
        async with self.source() as source:
            if isinstance(source, AsyncImageInspector):
                return await source.grep(
                    pattern,
                    path=path,
                    glob=glob,
                    max_count=max_count,
                    max_total=max_total,
                    case=case,
                    before=before,
                    after=after,
                )
            return await self.client.inspect_instance_grep(
                source,
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
        async with self.source() as source:
            if isinstance(source, AsyncImageInspector):
                return await source.read_file(path)
            return await self.client.inspect_instance_download(source, path)

    async def download_file(self, path: str, destination: str | Path) -> int:
        """Download atomically; leave destination unchanged if the transfer fails.

        Returns:
            The number of downloaded bytes.

        """
        async with self.source() as source:
            if isinstance(source, AsyncImageInspector):
                return await source.download_file(path, destination)
            async with aclosing(self.client.inspect_instance_download_stream(source, path)) as chunks:
                return await write_download_async(chunks, destination, path=path, on_progress=self.on_progress)

    async def file_exists(self, path: str) -> bool:
        async with self.source() as source:
            if isinstance(source, AsyncImageInspector):
                return await source.file_exists(path)
            return await self.client.check_instance_file(source, path)

    async def archive_exists(self, path: str) -> bool:
        async with self.source() as source:
            if isinstance(source, AsyncImageInspector):
                return await source.archive_exists(path)
            return await self.client.check_instance_archive(source, path)

    async def iter_file(self, path: str) -> AsyncGenerator[bytes, None]:
        """Stream one source. Close the generator if iteration stops early.

        Yields:
            File content chunks while the source remains reserved.

        """
        async with self.source() as source:
            chunks = (
                source.iter_file(path)
                if isinstance(source, AsyncImageInspector)
                else self.client.inspect_instance_download_stream(source, path)
            )
            async with aclosing(chunks):
                async for chunk in chunks:
                    yield chunk  # noqa: ASYNC119 - caller closes the generator

    async def archive(self, path: str, *, compressed: bool = False) -> AsyncGenerator[bytes, None]:
        """Stream tar content. Close the generator if iteration stops early.

        Yields:
            Archive chunks; compressed=True retains server compression.

        """
        async with self.source() as source:
            chunks = (
                source.archive(path, compressed=compressed)
                if isinstance(source, AsyncImageInspector)
                else self.client.inspect_instance_archive(source, path, compressed=compressed)
            )
            async with aclosing(chunks):
                async for chunk in chunks:
                    yield chunk  # noqa: ASYNC119 - caller closes the generator
