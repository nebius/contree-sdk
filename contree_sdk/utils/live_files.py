"""Helpers for applying uploaded files to a live VM."""

from __future__ import annotations

import asyncio
import tarfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path, PurePosixPath
from typing import TypeVar

from contree_client.exceptions import ConflictError, TooEarlyError

from contree_sdk.session.base import subprocess_not_ready
from contree_sdk.session.defaults import DEFAULT_READINESS_TIMEOUT, READINESS_RETRY_INTERVAL


T = TypeVar("T")


def validate_remote_path(path: str) -> None:
    if not PurePosixPath(path).is_absolute() or "\0" in path:
        raise ValueError("file paths must be absolute and contain no NUL characters")


def _file_not_ready(error: Exception, deadline: float) -> bool:
    return time.monotonic() < deadline and (
        subprocess_not_ready(error)
        or (
            isinstance(error, TooEarlyError)
            and any(
                message in str(error)
                for message in ("Instance has not started", "Instance inspection is not available", "NotReady")
            )
        )
    )


def ready_call(call: Callable[[], T]) -> T:
    deadline = time.monotonic() + DEFAULT_READINESS_TIMEOUT
    while True:
        try:
            return call()
        except (TooEarlyError, ConflictError) as error:  # noqa: PERF203 - retry only explicit readiness failures
            if not _file_not_ready(error, deadline):
                raise
            time.sleep(min(READINESS_RETRY_INTERVAL, max(0, deadline - time.monotonic())))


async def ready_call_async(call: Callable[[], Awaitable[T]]) -> T:
    deadline = time.monotonic() + DEFAULT_READINESS_TIMEOUT
    while True:
        try:
            return await call()
        except (TooEarlyError, ConflictError) as error:  # noqa: PERF203 - retry only explicit readiness failures
            if not _file_not_ready(error, deadline):
                raise
            await asyncio.sleep(min(READINESS_RETRY_INTERVAL, max(0, deadline - time.monotonic())))


def pack_upload(source: Path, destination: Path, *, name: str = ".") -> None:
    with tarfile.open(destination, "w:gz", dereference=name != ".") as archive:
        archive.add(source, arcname=name)
