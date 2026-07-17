from os import fdopen, pipe
from pathlib import Path
from typing import Literal, TypeAlias

from contree_sdk.utils.typing import AsyncReadable, AsyncWritable, Readable, Writable


class PipeIO:
    def __init__(self) -> None:
        super().__init__()
        r, w = pipe()
        self._r = fdopen(r, "rb", buffering=0)
        self._w = fdopen(w, "wb", buffering=0)

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


PipeLiteral = Literal[-1]  # subprocess.PIPE

INPUT_TYPES: TypeAlias = str | bytes | Path | Readable | AsyncReadable
OUTPUT_TYPES: TypeAlias = str | bytes | Path | Writable | AsyncWritable

OUTPUT_REQUEST_TYPES: TypeAlias = str | Path | Writable | AsyncWritable | PipeLiteral | type[str | bytes]
