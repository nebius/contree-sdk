"""Archive helpers and safe readiness waits for live filesystem transfers."""

from __future__ import annotations

import asyncio
import logging
import tarfile
import time
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Generator, Iterator
from pathlib import Path, PurePosixPath
from typing import TypeVar

from contree_client.exceptions import ConflictError, TooEarlyError

from contree_sdk.session.base import subprocess_not_ready
from contree_sdk.session.defaults import DEFAULT_READINESS_TIMEOUT, READINESS_RETRY_INTERVAL


T = TypeVar("T")
log = logging.getLogger(__name__)


def validate_remote_path(path: str) -> None:
    if not PurePosixPath(path).is_absolute() or "\0" in path:
        raise ValueError("file paths must be absolute and contain no NUL characters")


def file_not_ready(error: Exception, deadline: float) -> bool:
    return time.monotonic() < deadline and (
        subprocess_not_ready(error)
        or (
            isinstance(error, TooEarlyError)
            and any(
                message in str(error)
                for message in (
                    "Instance has not started",
                    "Instance inspection is not available",
                    "NotReady",
                )
            )
        )
    )


def ready_call(call: Callable[[], T]) -> T:
    deadline = time.monotonic() + DEFAULT_READINESS_TIMEOUT
    while True:
        try:
            return call()
        except (TooEarlyError, ConflictError) as error:  # noqa: PERF203 - retry only explicit pre-admission rejection
            if not file_not_ready(error, deadline):
                raise
            time.sleep(min(READINESS_RETRY_INTERVAL, max(0, deadline - time.monotonic())))


async def ready_call_async(call: Callable[[], Awaitable[T]]) -> T:
    deadline = time.monotonic() + DEFAULT_READINESS_TIMEOUT
    while True:
        try:
            return await call()
        except (TooEarlyError, ConflictError) as error:  # noqa: PERF203 - retry only explicit pre-admission rejection
            if not file_not_ready(error, deadline):
                raise
            await asyncio.sleep(min(READINESS_RETRY_INTERVAL, max(0, deadline - time.monotonic())))


def ready_stream(source: Callable[[], Iterator[bytes]]) -> Generator[bytes, None, None]:
    deadline = time.monotonic() + DEFAULT_READINESS_TIMEOUT
    delivered = False
    while True:
        try:  # noqa: PLW0717 - readiness retry owns iterator lifetime
            chunks = source()
            try:
                for chunk in chunks:
                    delivered = True
                    yield chunk
            finally:
                close = getattr(chunks, "close", None)
                if close is not None:
                    close()
        except (TooEarlyError, ConflictError) as error:  # noqa: PERF203 - retry only explicit pre-admission rejection
            if delivered or not file_not_ready(error, deadline):
                raise
            time.sleep(min(READINESS_RETRY_INTERVAL, max(0, deadline - time.monotonic())))
        else:
            return


async def ready_stream_async(source: Callable[[], AsyncIterator[bytes]]) -> AsyncGenerator[bytes, None]:
    deadline = time.monotonic() + DEFAULT_READINESS_TIMEOUT
    delivered = False
    while True:
        try:  # noqa: PLW0717 - readiness retry owns iterator lifetime
            chunks = source()
            try:
                async for chunk in chunks:
                    delivered = True
                    yield chunk
            finally:
                close = getattr(chunks, "aclose", None)
                if close is not None:
                    await close()
        except (TooEarlyError, ConflictError) as error:  # noqa: PERF203 - retry only explicit pre-admission rejection
            if delivered or not file_not_ready(error, deadline):
                raise
            await asyncio.sleep(min(READINESS_RETRY_INTERVAL, max(0, deadline - time.monotonic())))
        else:
            return


def pack_upload(source: Path, destination: Path, *, name: str = ".") -> None:
    with tarfile.open(destination, "w:gz", dereference=name != ".") as archive:
        archive.add(source, arcname=name)


def extract_download(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(source, "r:*") as archive:
        for member in archive:
            try:
                archive.extract(member, destination, filter="data")
            except tarfile.FilterError:  # noqa: PERF203 - validate each archive entry independently
                log.warning("Skipping unsafe archive member %s", member.name)
