from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from contree_sdk.api.models.file import FileItemModel
from contree_sdk.sdk.objects.image_like._base import DirTypeT, FileTypeT, _ImageLikeBase


@dataclass
class _ImageFsEntryBase(FileItemModel):
    _image: _ImageLikeBase
    _path: Path

    @property
    def full_path(self) -> Path:
        return self._path.joinpath(self.path)

    @property
    def is_file(self):
        return not self.is_dir


@dataclass
class _ImageFileBase(_ImageFsEntryBase):
    is_dir: Literal[False]


@dataclass
class _ImageDirectoryBase(_ImageFsEntryBase):
    is_dir: Literal[True]

    async def _ls(
        self, path: str | Path, file_type: type[FileTypeT], dir_type: type[DirTypeT]
    ) -> list[FileTypeT | DirTypeT]:
        return await self._image._ls(self.full_path.joinpath(path), file_type, dir_type)
