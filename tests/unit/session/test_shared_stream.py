"""Each Operation owns one transport subscription, including concurrent consumers."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from contree_sdk.session.operation_async import AsyncOperation
from contree_sdk.session.operation_sync import Operation
from tests.unit.session.lazy_clients import LiveAsyncClient, LiveClient, event


def sequence():
    return [
        replace(event("stdout", 1), id=1),
        replace(event("stdout", 2), id=2),
        replace(event("exit", 2), id=3),
        replace(event("completion"), id=4, spid=...),
    ]


def test_sync_wait_events_subprocess_and_replay_share_one_reader():
    client = LiveClient()
    client.auto_exit = False
    client.spawn_instance("sleep", "base")
    expected = sequence()
    with Operation(client, "op-1") as operation, ThreadPoolExecutor(4) as pool:
        handle = operation.run("echo")
        all_events = pool.submit(lambda: list(operation.events()))
        filtered = pool.submit(lambda: list(operation.events(since=1, spid=2)))
        result = pool.submit(operation.wait, timeout=2)
        subprocess_result = pool.submit(handle.wait, timeout=2)
        for item in expected:
            client.streams["op-1"].put(item)
        assert all_events.result(2) == expected
        assert filtered.result(2) == expected[1:3]
        assert result.result(2) == operation.wait()
        assert subprocess_result.result(2) == handle.wait()
        assert list(operation.events(since=2)) == expected[2:]
    assert len(client.calls_for("follow_operation_events")) == 1
    assert client.calls_for("follow_operation_events")[0].kwargs == {}
    assert len(client.calls_for("get_operation_status")) == 1
    assert not client.calls_for("wait_operation")
    assert operation.consumer_thread is not None
    assert not operation.consumer_thread.is_alive()


async def collect(operation, **kwargs):
    return [item async for item in operation.events(**kwargs)]


async def test_async_wait_events_subprocess_and_replay_share_one_reader():
    client = LiveAsyncClient()
    client.auto_exit = False
    await client.spawn_instance("sleep", "base")
    expected = sequence()
    async with AsyncOperation(client, "op-1") as operation:
        handle = await operation.run("echo")
        all_events = asyncio.create_task(collect(operation))
        filtered = asyncio.create_task(collect(operation, since=1, spid=2))
        result = asyncio.create_task(operation.wait(timeout=2))
        subprocess_result = asyncio.create_task(handle.wait(timeout=2))
        for item in expected:
            await client.streams["op-1"].put(item)
        assert await all_events == expected
        assert await filtered == expected[1:3]
        assert await result == await operation.wait()
        assert await subprocess_result == await handle.wait()
        assert await collect(operation, since=2) == expected[2:]
    assert len(client.calls_for("follow_operation_events")) == 1
    assert client.calls_for("follow_operation_events")[0].kwargs == {}
    assert len(client.calls_for("get_operation_status")) == 1
    assert not client.calls_for("wait_operation")
    assert operation.consumer_task is not None
    assert operation.consumer_task.done()


async def test_cancelled_event_subscriber_leaves_reader_available():
    client = LiveAsyncClient()
    await client.spawn_instance("sleep", "base")
    operation = AsyncOperation(client, "op-1")
    subscriber = asyncio.create_task(collect(operation))
    await asyncio.sleep(0)
    subscriber.cancel()
    with pytest.raises(asyncio.CancelledError):
        await subscriber
    assert not client.calls_for("cancel_operation")
    await client.streams["op-1"].put(event("completion"))
    await operation.wait(timeout=1)
    assert len(await collect(operation)) == 1
    assert len(client.calls_for("follow_operation_events")) == 1
    await operation.shutdown()


def test_sync_stream_error_reaches_all_consumers_and_late_subscribers():
    client = LiveClient()
    client.auto_exit = False
    client.spawn_instance("sleep", "base")
    operation = Operation(client, "op-1")
    operation.__enter__()  # noqa: PLC2801 - assert shutdown error separately
    handle = operation.run("sleep")
    failure = OSError("lost stream")
    client.streams["op-1"].put(failure)
    with pytest.raises(OSError, match="lost stream"):
        operation.wait(timeout=1)
    with pytest.raises(OSError, match="lost stream"):
        list(operation.events())
    with pytest.raises(OSError, match="lost stream"):
        handle.wait(timeout=1)
    with pytest.raises(OSError, match="lost stream"):
        operation.shutdown()
    assert len(client.calls_for("follow_operation_events")) == 1
    assert not client.calls_for("get_operation_status")


async def test_async_stream_error_reaches_all_consumers_and_late_subscribers():
    client = LiveAsyncClient()
    client.auto_exit = False
    await client.spawn_instance("sleep", "base")
    operation = AsyncOperation(client, "op-1")
    await operation.__aenter__()  # noqa: PLC2801 - assert shutdown error separately
    handle = await operation.run("sleep")
    await client.streams["op-1"].put(OSError("lost stream"))
    with pytest.raises(OSError, match="lost stream"):
        await operation.wait(timeout=1)
    with pytest.raises(OSError, match="lost stream"):
        await collect(operation)
    with pytest.raises(OSError, match="lost stream"):
        await handle.wait(timeout=1)
    with pytest.raises(OSError, match="lost stream"):
        await operation.shutdown()
    assert len(client.calls_for("follow_operation_events")) == 1
    assert not client.calls_for("get_operation_status")


def test_sync_timeout_cancels_remote_without_starting_another_reader():
    client = LiveClient()
    client.spawn_instance("sleep", "base")
    operation = Operation(client, "op-1")
    with pytest.raises(TimeoutError):
        operation.wait(timeout=0.01)
    operation.shutdown()
    assert len(client.calls_for("cancel_operation")) == 1
    assert len(client.calls_for("follow_operation_events")) == 1


async def test_async_cancelled_wait_cancels_remote_without_cancelling_reader():
    client = LiveAsyncClient()
    await client.spawn_instance("sleep", "base")
    operation = AsyncOperation(client, "op-1")
    waiter = asyncio.create_task(operation.wait())
    await asyncio.sleep(0)
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    await operation.shutdown()
    assert len(client.calls_for("cancel_operation")) == 1
    assert len(client.calls_for("follow_operation_events")) == 1


def test_sync_subscription_timeout_leaves_reader_and_operation_available():
    client = LiveClient()
    client.spawn_instance("sleep", "base")
    operation = Operation(client, "op-1")
    with pytest.raises(TimeoutError):
        list(operation.events(timeout=0.01))
    assert not client.calls_for("cancel_operation")
    client.streams["op-1"].put(event("completion"))
    operation.wait(timeout=1)
    assert len(list(operation.events())) == 1
    assert len(client.calls_for("follow_operation_events")) == 1
    operation.shutdown()


async def test_async_subscription_timeout_leaves_reader_and_operation_available():
    client = LiveAsyncClient()
    await client.spawn_instance("sleep", "base")
    operation = AsyncOperation(client, "op-1")
    with pytest.raises(asyncio.TimeoutError):
        await collect(operation, timeout=0.01)
    assert not client.calls_for("cancel_operation")
    await client.streams["op-1"].put(event("completion"))
    await operation.wait(timeout=1)
    assert len(await collect(operation)) == 1
    assert len(client.calls_for("follow_operation_events")) == 1
    await operation.shutdown()
