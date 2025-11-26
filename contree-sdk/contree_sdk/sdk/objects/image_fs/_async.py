from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from contree_sdk.sdk.objects.image_fs._base import _ImageDirectoryBase, _ImageFileBase


@dataclass
class ImageFile(_ImageFileBase): ...


@dataclass
class ImageDirectory(_ImageDirectoryBase):
    async def ls(self, path: str | Path = "") -> list[ImageFile | ImageDirectory]:
        return await self._ls(path, ImageFile, ImageDirectory)
