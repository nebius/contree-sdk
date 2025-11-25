from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from contree_sdk.api.models.file import FileItemModel
from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase


@dataclass
class _ImageFsEntryBase(FileItemModel):
    _image: _ImageLikeBase
    _path: Path

    @property
    def full_path(self) -> Path:
        return self._path.joinpath(self.path)


@dataclass
class _ImageFileBase(_ImageFsEntryBase):
    is_dir: Literal[False]


@dataclass
class _ImageDirectoryBase(_ImageFsEntryBase):
    is_dir: Literal[True]
