"""Transfer progress and atomic local download writers."""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import AsyncIterable, Callable, Iterable, Iterator
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import IO, Any, Literal, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class TransferProgress:
    """Completed upload size or cumulative downloaded bytes for one remote path."""

    direction: Literal["upload", "download"]
    path: str
    bytes_transferred: int
    total_bytes: int | None = None


ProgressCallback = Callable[[TransferProgress], None]


async def run_file_io(function: Callable[..., T], *args: Any) -> T:
    """Join local I/O before propagating cancellation.

    Returns:
        The function result.

    Raises:
        asyncio.CancelledError: The caller cancelled the task; local I/O has finished.

    """
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            with suppress(BaseException):
                await asyncio.shield(task)
        with suppress(BaseException):
            task.result()
        raise


def hash_upload(handle: IO[bytes]) -> str:
    position = handle.tell()
    digest = hashlib.sha256()
    try:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    finally:
        handle.seek(position)
    return digest.hexdigest()


@contextmanager
def download_target(destination: str | Path) -> Iterator[IO[bytes]]:
    """Keep the old destination until the temporary sibling is complete.

    Yields:
        A temporary file. Normal exit replaces the destination; exceptions remove it.

    """
    target = Path(destination)
    with NamedTemporaryFile(dir=target.parent, prefix=f".{target.name}.", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            yield handle
            handle.close()
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)


def flush_download(handle: IO[bytes]) -> None:
    handle.flush()
    os.fsync(handle.fileno())


def write_download(
    chunks: Iterable[bytes], destination: str | Path, *, path: str = "", on_progress: ProgressCallback | None = None
) -> int:
    """Write streamed bytes atomically; preserve the destination on failure.

    Returns:
        The number of downloaded bytes.

    """
    total = 0
    with download_target(destination) as handle:
        for chunk in chunks:
            handle.write(chunk)
            total += len(chunk)
            if on_progress is not None:
                on_progress(TransferProgress("download", path, total))
        flush_download(handle)
    return total


async def write_download_async(
    chunks: AsyncIterable[bytes],
    destination: str | Path,
    *,
    path: str = "",
    on_progress: ProgressCallback | None = None,
) -> int:
    """Write streamed bytes atomically, joining local writes before cancellation escapes.

    Returns:
        The number of downloaded bytes.

    """
    total = 0
    with download_target(destination) as handle:
        async for chunk in chunks:
            await run_file_io(handle.write, chunk)
            total += len(chunk)
            if on_progress is not None:
                on_progress(TransferProgress("download", path, total))
        await run_file_io(flush_download, handle)
    return total
