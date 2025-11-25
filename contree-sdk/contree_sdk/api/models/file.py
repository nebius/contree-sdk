from dataclasses import dataclass


@dataclass
class FileItemModel:
    size: int
    path: str
    uid: int
    gid: int
    mode: int
    mtime: int
    nlink: int
    symlink_to: str
    is_dir: bool
    is_regular: bool
    is_socket: bool
    is_fifo: bool
    is_symlink: bool
    owner: str
    group: str
