from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal


@dataclass
class FileItemModel:
    """Mirrors `contree_client.models.FileItem` field-for-field.

    Kept as a plain dataclass here (rather than importing `FileItem`
    directly) so `ImageFsEntryBase` can add its own `image`/`base_path`
    fields on top via normal dataclass inheritance.
    """

    size: int
    path: str
    owner: str | int
    group: str | int
    uid: int
    gid: int
    mode: int
    mtime: int
    nlink: int
    is_dir: bool
    is_regular: bool
    is_symlink: bool
    is_socket: bool
    is_fifo: bool
    symlink_to: str


@dataclass
class ImageFsEntryBase(FileItemModel):
    # loosely typed: the concrete sync/async image-like object defines
    # `read`/`download`/`list_entries`, not the shared `ImageLikeBase`
    image: Any
    base_path: PurePosixPath

    @property
    def full_path(self) -> PurePosixPath:
        return self.base_path.joinpath(self.path)

    @property
    def name(self) -> str:
        return self.full_path.name

    @property
    def is_file(self):
        return not self.is_dir


@dataclass
class ImageFileBase(ImageFsEntryBase):
    is_dir: Literal[False]  # pyright: ignore[reportIncompatibleVariableOverride]


@dataclass
class ImageDirectoryBase(ImageFsEntryBase):
    is_dir: Literal[True]  # pyright: ignore[reportIncompatibleVariableOverride]
