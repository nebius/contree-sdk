from pathlib import Path

from contree_sdk.sdk.objects.image_fs._async import ImageDirectory, ImageFile
from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase


class _ImageLike(_ImageLikeBase):
    """Asynchronous image-like object for command execution."""

    def __await__(self):
        return self._await().__await__()

    async def ls(self, path: str | Path = "/") -> list[ImageFile | ImageDirectory]:
        """List files and directories at the given path.

        Args:
            path: Path inside the image to list.

        Returns:
            List of ImageFile and ImageDirectory objects.

        """
        return await self._ls(path, ImageFile, ImageDirectory)

    async def download(self, image_path: str | Path, local_path: str | Path | None = None) -> Path | None:
        """Download a file from the image to local filesystem.

        Args:
            image_path: Path to the file inside the image.
            local_path: Local destination path. Defaults to filename from image_path.

        Returns:
            Path to the downloaded file.

        """
        return await self._download(image_path, local_path)

    async def read(self, image_path: str | Path | None = None) -> bytes:
        """Read file contents from the image.

        Args:
            image_path: Path to the file inside the image.

        Returns:
            File contents as bytes.

        """
        return await self._read_file(image_path)
