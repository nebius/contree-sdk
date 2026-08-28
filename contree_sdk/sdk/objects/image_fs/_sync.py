from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from contree_sdk.sdk.objects.image_fs._base import ImageDirectoryBase, ImageFileBase


@dataclass
class ImageFileSync(ImageFileBase):
    def read(self) -> bytes:
        return self.image.read(self.full_path)

    def download(self, local_path: str | Path | None = None) -> Path:
        return self.image.download(self.full_path, local_path)


@dataclass
class ImageDirectorySync(ImageDirectoryBase):
    def ls(self, path: str | PurePosixPath = "") -> list[ImageFileSync | ImageDirectorySync]:
        return self.image.list_entries(self.full_path.joinpath(path), ImageFileSync, ImageDirectorySync)
