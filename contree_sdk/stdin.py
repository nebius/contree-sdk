"""Input sources, local readers, and values shared by stdin forwarding."""

from __future__ import annotations

from asyncio import to_thread
from collections.abc import Iterator
from dataclasses import dataclass
from inspect import iscoroutinefunction
from pathlib import Path
from typing import Protocol, TypeAlias, TypeVar, cast


DEFAULT_STDIN_CHUNK_SIZE = 64 * 1024
DataT_co = TypeVar("DataT_co", str, bytes, covariant=True)


class Readable(Protocol[DataT_co]):
    def read(self, size: int = -1, /) -> DataT_co: ...


class AsyncReadable(Protocol[DataT_co]):
    async def read(self, size: int = -1, /) -> DataT_co: ...


InputSource: TypeAlias = (
    str | bytes | Path | Readable[str] | Readable[bytes] | AsyncReadable[str] | AsyncReadable[bytes]
)


def read_stdin(source: InputSource) -> str | bytes:
    if isinstance(source, (str, bytes)):
        return source
    if isinstance(source, Path):
        return source.read_bytes()
    if iscoroutinefunction(source.read):
        raise TypeError("an async-readable stdin source requires an async session")
    return cast("str | bytes", source.read())


async def read_stdin_async(source: InputSource) -> str | bytes:
    if isinstance(source, (str, bytes)):
        return source
    if isinstance(source, Path):
        return await to_thread(source.read_bytes)
    if iscoroutinefunction(source.read):
        return cast("str | bytes", await source.read())
    return cast("str | bytes", await to_thread(source.read))


@dataclass(frozen=True)
class StdinResult:
    """Acknowledged input bytes and whether EOF was sent or the process ended.

    A successful write does not prove that the remote process read the bytes.
    An ambiguous transport error raises instead of returning a partial result.
    """

    bytes_sent: int = 0
    eof_sent: bool = False
    process_exited: bool = False


def stdin_chunks(data: str | bytes, chunk_size: int) -> Iterator[bytes]:
    """Split input without allocating an encoded copy of the complete string.

    Yields:
        Byte chunks of at most chunk_size bytes.

    Raises:
        TypeError: A source chunk is neither str nor bytes.

    """
    if not isinstance(data, (str, bytes)):
        raise TypeError("stdin chunks must be str or bytes")
    for offset in range(0, len(data), chunk_size):
        part = data[offset : offset + chunk_size]
        encoded = part.encode() if isinstance(part, str) else part
        for start in range(0, len(encoded), chunk_size):
            yield encoded[start : start + chunk_size]
