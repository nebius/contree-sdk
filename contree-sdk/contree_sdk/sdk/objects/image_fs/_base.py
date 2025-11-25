from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase


class _ImageFsEntryBase:
    _image: _ImageLikeBase
    _path: Path
    path: str
    size: int

    mode: int  # todo find better type for mode
    owner: int
    group: int

    is_dir: bool
    is_regular: bool
    is_simlink: bool
    is_socket: bool
    is_fifo: bool
    symlink_to: str


@dataclass
class _ImageFileBase(_ImageFsEntryBase):
    is_dir: Literal[False]
    is_file: Literal[True]

    async def _download(self, local_path: str | Path):
        pass
        # todo download


@dataclass
class _ImageDirectoryBase(_ImageFsEntryBase):
    is_dir: Literal[True]
    is_file: Literal[False]

    async def _ls(self, path: str | Path):
        # todo connect paths properly
        return await self._image._ls(self._path + path)

    # "mtime": 1640995200,
