"""Read-only inspection of one saved ConTree image.

Inspectors pin an image UUID. They borrow their client and file transfer, and do
not track later session changes. Paths use the image root, not the session cwd.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator, Sequence
from contextlib import aclosing, closing
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from contree_client.models import DirectoryList, GrepResult, Image
from contree_client.types import ContreeAsyncClient, ContreeSyncClient

from contree_sdk.files import AsyncFileTransfer, SyncFileTransfer


@dataclass(frozen=True)
class ImageInspector:
    """Inspect one saved image using caller-owned resources."""

    client: ContreeSyncClient
    image_uuid: str
    file_transfer: SyncFileTransfer

    def info(self) -> Image:
        """Return the saved image's metadata.

        Returns:
            Image metadata from ConTree.

        """
        return self.client.inspect_image(self.image_uuid)

    def list(self, path: str = "/") -> DirectoryList:
        """Return directory entries with size, permissions, owner, and file type.

        Returns:
            Directory entries and their filesystem metadata.

        """
        return self.client.inspect_image_list(self.image_uuid, path)

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
        """Search file contents with the client's ripgrep syntax and limits.

        Returns:
            Matching lines and search summary from ConTree.

        """
        return self.client.inspect_image_grep(
            self.image_uuid,
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
        """Return the complete file contents through the supplied file transfer.

        Returns:
            The complete file as bytes.

        """
        return self.file_transfer.read_file(self.image_uuid, path)

    def download_file(self, path: str, destination: str | Path) -> int:
        """Save a file atomically and return the number of downloaded bytes.

        Returns:
            The number of downloaded bytes.

        """
        return self.file_transfer.download_file(self.image_uuid, path, destination)

    def file_exists(self, path: str) -> bool:
        """Check for a downloadable file without fetching its contents.

        Returns:
            True if the file exists; False for a missing path.

        """
        return self.client.check_image_file(self.image_uuid, path)

    def archive_exists(self, path: str) -> bool:
        """Check whether a file or directory can be downloaded as an archive.

        Returns:
            True if the path can be archived; False for a missing path.

        """
        return self.client.check_image_archive(self.image_uuid, path)

    def iter_file(self, path: str) -> Generator[bytes, None, None]:
        """Stream file contents. Close the generator if iteration stops early.

        Yields:
            File content chunks from the pinned image.

        """
        with closing(self.file_transfer.iter_file(self.image_uuid, path)) as chunks:
            yield from chunks

    def archive(self, path: str, *, compressed: bool = False) -> Generator[bytes, None, None]:
        """Stream a path as tar. compressed=True retains server compression.

        Yields:
            Archive chunks. Close the generator if iteration stops early.

        """
        chunks = self.client.inspect_image_archive(self.image_uuid, path, compressed=compressed)
        try:
            yield from chunks
        finally:
            close = getattr(chunks, "close", None)
            if close is not None:
                close()


@dataclass(frozen=True)
class AsyncImageInspector:
    """Inspect one saved image using caller-owned resources."""

    client: ContreeAsyncClient
    image_uuid: str
    file_transfer: AsyncFileTransfer

    async def info(self) -> Image:
        """Return the saved image's metadata.

        Returns:
            Image metadata from ConTree.

        """
        return await self.client.inspect_image(self.image_uuid)

    async def list(self, path: str = "/") -> DirectoryList:
        """Return directory entries with size, permissions, owner, and file type.

        Returns:
            Directory entries and their filesystem metadata.

        """
        return await self.client.inspect_image_list(self.image_uuid, path)

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
        """Search file contents with the client's ripgrep syntax and limits.

        Returns:
            Matching lines and search summary from ConTree.

        """
        return await self.client.inspect_image_grep(
            self.image_uuid,
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
        """Return the complete file contents through the supplied file transfer.

        Returns:
            The complete file as bytes.

        """
        return await self.file_transfer.read_file(self.image_uuid, path)

    async def download_file(self, path: str, destination: str | Path) -> int:
        """Save a file atomically and return the number of downloaded bytes.

        Returns:
            The number of downloaded bytes.

        """
        return await self.file_transfer.download_file(self.image_uuid, path, destination)

    async def file_exists(self, path: str) -> bool:
        """Check for a downloadable file without fetching its contents.

        Returns:
            True if the file exists; False for a missing path.

        """
        return await self.client.check_image_file(self.image_uuid, path)

    async def archive_exists(self, path: str) -> bool:
        """Check whether a file or directory can be downloaded as an archive.

        Returns:
            True if the path can be archived; False for a missing path.

        """
        return await self.client.check_image_archive(self.image_uuid, path)

    async def iter_file(self, path: str) -> AsyncGenerator[bytes, None]:
        """Stream file contents. Close the generator if iteration stops early.

        Yields:
            File content chunks from the pinned image.

        """
        async with aclosing(self.file_transfer.iter_file(self.image_uuid, path)) as chunks:
            async for chunk in chunks:
                yield chunk  # noqa: ASYNC119 - caller closes the generator

    async def archive(self, path: str, *, compressed: bool = False) -> AsyncGenerator[bytes, None]:
        """Stream a path as tar. compressed=True retains server compression.

        Yields:
            Archive chunks. Close the generator if iteration stops early.

        """
        async with aclosing(self.client.inspect_image_archive(self.image_uuid, path, compressed=compressed)) as chunks:
            async for chunk in chunks:
                yield chunk  # noqa: ASYNC119 - caller closes the generator
