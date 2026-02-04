from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from contree_sdk.sdk.objects.image_fs._base import _ImageDirectoryBase, _ImageFileBase


@dataclass
class ImageFile(_ImageFileBase):
    async def read(self) -> bytes:
        return await self._image._read_file(self.full_path)

    async def download(self, local_path: str | Path | None = None) -> Path:
        return await self._image._download(self.full_path, local_path)


@dataclass
class ImageDirectory(_ImageDirectoryBase):
    async def ls(self, path: str | PurePosixPath = "") -> list[ImageFile | ImageDirectory]:
        return await self._ls(path, ImageFile, ImageDirectory)
