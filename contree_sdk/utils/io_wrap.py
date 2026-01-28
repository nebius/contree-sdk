from io import BytesIO, IOBase, StringIO
from os import fdopen, pipe
from pathlib import Path
from subprocess import PIPE
from typing import IO, AnyStr, Literal

from strenum import StrEnum


class PipeIO(IOBase):
    def __init__(self) -> None:
        super().__init__()
        r, w = pipe()
        self._r = fdopen(r, "rb", buffering=0)
        self._w = fdopen(w, "wb", buffering=0)

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return False

    def read(self, size: int = -1) -> bytes:
        return self._r.read(size)

    def readline(self, size: int | None = -1) -> bytes:
        return self._r.readline(size)

    def write(self, b: bytes) -> int:
        return self._w.write(b)

    def flush(self) -> None:
        self._w.flush()

    def close(self) -> None:
        if not self._w.closed:
            self._w.close()
            return
        self._r.close()

    @property
    def closed(self) -> bool:
        return self._w.closed and self._r.closed


class IOMode(StrEnum):
    read = "r"
    write = "w"


PipeLiteral = Literal[-1]  # subprocess.PIPE
IO_TYPES = str | bytes | Path | IO[AnyStr] | PipeLiteral


def get_io_by_obj(obj: IO_TYPES | None, mode: IOMode) -> IOBase | IO | None:
    if obj is None:
        return None
    if obj is PIPE:
        return PipeIO()
    if isinstance(obj, IOBase):
        return obj
    if isinstance(obj, bytes):
        if mode != IOMode.read:
            raise TypeError("bytes cannot be used as output")
        return BytesIO(obj)
    if isinstance(obj, str):
        if mode == IOMode.read:
            return StringIO(obj)
        obj = Path(obj)
    if not isinstance(obj, Path):
        raise TypeError(f"{obj} is not supported as IO")
    file_mode = mode + "b"
    return obj.open(file_mode)
