from dataclasses import dataclass


@dataclass
class FileItem:
    size: int
    path: str
    owner: int
    group: int
    mode: int
    mtime: int
    is_dir: bool
    is_regular: bool
    is_symlink: bool
    is_socket: bool
    is_fifo: bool
    symlink_to: str


@dataclass
class DirectoryList:
    path: str
    files: list[FileItem]
