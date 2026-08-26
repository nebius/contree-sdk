from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from contree_sdk.sdk.objects.image_fs._base import ImageDirectoryBase, ImageFileBase


@dataclass
class ImageFile(ImageFileBase):
    async def read(self) -> bytes:
        return await self.image.read(self.full_path)

    async def download(self, local_path: str | Path | None = None) -> Path:
        return await self.image.download(self.full_path, local_path)


@dataclass
class ImageDirectory(ImageDirectoryBase):
    async def ls(self, path: str | PurePosixPath = "") -> list[ImageFile | ImageDirectory]:
        return await self.image.list_entries(self.full_path.joinpath(path), ImageFile, ImageDirectory)
