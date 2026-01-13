import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass
class UploadedFile:
    uuid: str
    sha256: str


DEFAULT_MODE = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH


@dataclass(kw_only=True)
class UploadFileSpec:
    uid: int = 0
    gid: int = 0
    mode: int = DEFAULT_MODE
    path: Path | str | None = None

    source: str | Path | UploadedFile
