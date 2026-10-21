import asyncio
import inspect

import pytest
from contree_client.exceptions import APIConnectionError, ConflictError, TooEarlyError
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk.session import AsyncOperation, Operation


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def operation(request):
    client = ContreeAsyncClient() if request.param else ContreeClient()
    handle = (AsyncOperation if request.param else Operation)(client, "op", readiness_timeout=0.01)
    handle.entered = True
    return client, handle


async def invoke(function, *args, **kwargs):
    result = function(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


async def test_pending_and_control_channel_rejections_preserve_request(operation):
    client, handle = operation
    handle.readiness_timeout = 1
    client.mock("operation_subprocess_create", error=ConflictError(409, "Operation is PENDING, not running"))
    client.mock("operation_subprocess_create", error=TooEarlyError(425, "control channel not connected"))
    client.mock(
        "operation_subprocess_create",
        error=TooEarlyError(425, "guest not ready: ('primary workload not started yet',)"),
    )
    client.mock("operation_subprocess_create", 2)
    child = await invoke(handle.run, "printf", args=iter(["hello"]), stdin=b"data", env={"X": "1"})
    calls = client.calls_for("operation_subprocess_create")
    assert child.spid == 2
    assert len(calls) == 4
    assert all(call.kwargs == calls[0].kwargs for call in calls)
    assert calls[0].kwargs["args"] == ["hello"]


@pytest.mark.parametrize(
    "error",
    [
        ConflictError(409, "already stopped"),
        TooEarlyError(425, "other precondition"),
        APIConnectionError("response lost"),
    ],
)
async def test_other_errors_are_not_retried(operation, error):
    client, handle = operation
    client.mock("operation_subprocess_create", error=error)
    with pytest.raises(type(error)) as caught:
        await invoke(handle.run, "true")
    assert caught.value is error
    assert len(client.calls_for("operation_subprocess_create")) == 1


async def test_readiness_wait_is_bounded(operation):
    client, handle = operation
    error = TooEarlyError(425, "control channel not connected")
    client.mock("operation_subprocess_create", error=error)
    with pytest.raises(TooEarlyError) as caught:
        await invoke(handle.run, "true")
    assert caught.value is error
    assert len(client.calls_for("operation_subprocess_create")) == 2


async def test_terminal_operation_does_not_retry(operation):
    client, handle = operation
    handle.terminal = True
    client.mock("operation_subprocess_create", error=TooEarlyError(425, "control channel not connected"))
    with pytest.raises(TooEarlyError):
        await invoke(handle.run, "true")
    assert len(client.calls_for("operation_subprocess_create")) == 1


async def test_async_readiness_wait_can_be_cancelled():
    client = ContreeAsyncClient()
    client.mock("operation_subprocess_create", error=TooEarlyError(425, "control channel not connected"))
    handle = AsyncOperation(client, "op")
    handle.entered = True
    task = asyncio.create_task(handle.run("true"))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(client.calls_for("operation_subprocess_create")) == 1
