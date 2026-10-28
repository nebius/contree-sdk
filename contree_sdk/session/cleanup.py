"""Cleanup boundaries for operation handles owned by SDK orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Coroutine, Iterator
from contextlib import asynccontextmanager, contextmanager, suppress

from contree_sdk.session.contracts import AsyncOperationContract, OperationContract


def _abort(operation: OperationContract) -> None:
    try:
        operation.cancel()
    finally:
        operation.shutdown()


async def _abort_async(operation: AsyncOperationContract) -> None:
    try:
        await operation.cancel()
    finally:
        await operation.shutdown()


async def await_cleanup(cleanup: Coroutine[object, object, None]) -> None:
    """Join cleanup despite repeated caller cancellation, then propagate cancellation.

    Raises:
        asyncio.CancelledError: The caller cancelled while cleanup was running.

    """
    task = asyncio.create_task(cleanup)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:  # noqa: PERF203 - handle each cancellation while joining cleanup
            cancelled = True
        except Exception:
            # Retrieve the error below, after deciding which error takes priority.
            break
    if cancelled:
        with suppress(Exception, asyncio.CancelledError):
            task.result()
        raise asyncio.CancelledError
    task.result()


@contextmanager
def owned_operation(operation: OperationContract) -> Iterator[OperationContract]:
    """Close an SDK-owned handle after use without starting its reader early.

    Yields:
        The same handle. A body error takes priority over cleanup errors.

    """
    try:
        yield operation
    except BaseException:
        with suppress(Exception):
            _abort(operation)
        raise
    else:
        operation.shutdown()


@asynccontextmanager
async def owned_async_operation(operation: AsyncOperationContract) -> AsyncIterator[AsyncOperationContract]:
    """Close an SDK-owned handle and join cleanup before propagating cancellation.

    Yields:
        The same handle. A body error takes priority over cleanup errors.

    """
    try:
        yield operation
    except BaseException:
        with suppress(Exception, asyncio.CancelledError):
            await await_cleanup(_abort_async(operation))
        raise
    else:
        await await_cleanup(operation.shutdown())
