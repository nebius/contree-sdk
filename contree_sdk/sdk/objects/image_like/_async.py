from collections.abc import AsyncIterator
from pathlib import Path, PurePosixPath
from typing import TypeVar

from contree_sdk._internals.io.operation_waiter import OutputChunk
from contree_sdk._internals.utils.typing import keep_signature
from contree_sdk.sdk.objects.image_fs._async import ImageDirectory, ImageFile
from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase


_T = TypeVar("_T", bound="_ImageLike")


class _ImageLike(_ImageLikeBase):
    """Asynchronous image-like object for command execution."""

    def __await__(self):
        return self._await().__await__()

    def __aiter__(self) -> AsyncIterator[OutputChunk]:
        return self._iter_output()

    @keep_signature(_ImageLikeBase._start)
    async def start(self: _T) -> _T:
        return await self._start()

    async def ls(self, path: str | PurePosixPath = "/") -> list[ImageFile | ImageDirectory]:
        """List files and directories at the given path.

        Args:
            path: Path inside the image to list.

        Returns:
            List of ImageFile and ImageDirectory objects.

        """
        return await self._ls(path, ImageFile, ImageDirectory)

    async def download(self, image_path: str | PurePosixPath, local_path: str | Path | None = None) -> Path | None:
        """Download a file from the image to local filesystem.

        Args:
            image_path: Path to the file inside the image.
            local_path: Local destination path. Defaults to filename from image_path.

        Returns:
            Path to the downloaded file.

        """
        return await self._download(image_path, local_path)

    async def read(self, image_path: str | PurePosixPath) -> bytes:
        """Read file contents from the image.

        Args:
            image_path: Path to the file inside the image.

        Returns:
            File contents as bytes.

        """
        return await self._read_file(image_path)

    @keep_signature(_ImageLikeBase._tag_as)
    async def tag_as(self: _T, tag: str | None) -> _T:
        return await self._tag_as(tag)

    @keep_signature(_ImageLikeBase._untag)
    async def untag(self: _T) -> _T:
        return await self._untag()

    @keep_signature(_ImageLikeBase._apply_files)
    async def apply_files(self: _T, *args, **kwargs) -> _T:
        return await self._apply_files(*args, **kwargs)
