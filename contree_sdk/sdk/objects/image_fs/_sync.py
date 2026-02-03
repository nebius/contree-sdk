from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from contree_sdk._internals.utils.wrapper import coro_sync
from contree_sdk.sdk.objects.image_fs._base import _ImageDirectoryBase, _ImageFileBase


@dataclass
class ImageFileSync(_ImageFileBase):
    def read(self) -> bytes:
        return coro_sync(self._image._read_file(self.full_path))

    def download(self, local_path: str | Path | None = None) -> Path:
        return coro_sync(self._image._download(self.full_path, local_path))


@dataclass
class ImageDirectorySync(_ImageDirectoryBase):
    def ls(self, path: str | PurePosixPath = "") -> list[ImageFileSync | ImageDirectorySync]:
        return coro_sync(self._ls(path, ImageFileSync, ImageDirectorySync))
