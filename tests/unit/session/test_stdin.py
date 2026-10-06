"""Stream stdin through the same operation reader used by wait and events."""

import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from contree_client.models import StreamRepr

from contree_sdk.session import ContreeAsyncSession, ContreeSession, StdinResult
from contree_sdk.session.base import exit_code_of
from tests.unit.session.lazy_clients import event
from tests.unit.session.stdin_clients import AsyncStdinClient, StdinClient


async def async_chunks(*items):
    for item in items:
        yield item


def assert_writes(client, payload, chunk_size):
    calls = client.calls_for("operation_subprocess_stdin")
    decoded = [StreamRepr(value=c.args[2], encoding=c.kwargs["encoding"]).as_bytes() for c in calls]
    assert b"".join(decoded) == payload
    assert max(map(len, decoded)) <= chunk_size
    assert not any(c.kwargs["close"] for c in calls[:-1])
    assert calls[-1].kwargs["close"]
    assert decoded[-1] == b""
    assert len(client.calls_for("follow_operation_events")) == 1
    assert client.calls_for("follow_operation_events")[0].kwargs == {}


@pytest.mark.parametrize("data", [b"", bytes(range(256)) * 8192, "Привет 🌎" * 8192])
def test_sync_bounded_input_and_explicit_eof(data):
    client = StdinClient()
    operation = ContreeSession(client, image="base").spawn("cat", stdin_open=True)
    assert client.calls_for("spawn_instance")[0].kwargs["stdin"].close is False
    payload = data.encode() if isinstance(data, str) else data
    assert operation.pipe_stdin([data], chunk_size=1024) == StdinResult(len(payload), eof_sent=True)
    assert exit_code_of(operation.wait(timeout=2)) == 0
    assert list(operation.events())[-1].type == "completion"
    assert_writes(client, payload, 1024)
    operation.shutdown()


@pytest.mark.parametrize("data", [b"", bytes(range(256)) * 8192, "Привет 🌎" * 8192])
async def test_async_bounded_input_and_explicit_eof(data):
    client = AsyncStdinClient()
    operation = await ContreeAsyncSession(client, image="base").spawn("cat", stdin_open=True)
    assert client.calls_for("spawn_instance")[0].kwargs["stdin"].close is False
    payload = data.encode() if isinstance(data, str) else data
    assert await operation.pipe_stdin(async_chunks(data), chunk_size=1024) == StdinResult(len(payload), eof_sent=True)
    assert exit_code_of(await operation.wait(timeout=2)) == 0
    assert [item.type async for item in operation.events()][-1] == "completion"
    assert_writes(client, payload, 1024)
    await operation.shutdown()


def test_sync_waits_for_spawn_before_requesting_delayed_input():
    client = StdinClient()
    client.ready = False
    operation = ContreeSession(client, image="base").spawn("cat", stdin_open=True)
    requested = threading.Event()
    available = threading.Event()

    def chunks():
        requested.set()
        assert available.wait(2)
        yield b"later"

    with ThreadPoolExecutor() as pool:
        result = pool.submit(operation.pipe_stdin, chunks())
        assert not requested.wait(0.02)
        client.streams[operation.uuid].put(event("spawn"))
        assert requested.wait(2)
        assert not client.calls_for("operation_subprocess_stdin")
        available.set()
        assert result.result(2).eof_sent
    operation.wait(timeout=2)
    operation.shutdown()


async def test_async_waits_for_spawn_before_requesting_delayed_input():
    client = AsyncStdinClient()
    client.ready = False
    operation = await ContreeAsyncSession(client, image="base").spawn("cat", stdin_open=True)
    requested = asyncio.Event()
    available = asyncio.Event()

    async def chunks():
        requested.set()
        await available.wait()
        yield b"later"

    result = asyncio.create_task(operation.pipe_stdin(chunks()))
    await asyncio.sleep(0)
    assert not requested.is_set()
    await client.streams[operation.uuid].put(event("spawn"))
    await asyncio.wait_for(requested.wait(), 2)
    assert not client.calls_for("operation_subprocess_stdin")
    available.set()
    assert (await asyncio.wait_for(result, 2)).eof_sent
    await operation.wait(timeout=2)
    await operation.shutdown()


def test_sync_exit_before_spawn_does_not_read_source():
    client = StdinClient()
    client.ready = False
    operation = ContreeSession(client, image="base").spawn("cat", stdin_open=True)

    def chunks():
        pytest.fail("source must not be read after exit")
        yield b"unreachable"

    client.streams[operation.uuid].put(event("completion"))
    assert operation.pipe_stdin(chunks()) == StdinResult(process_exited=True)
    assert not client.calls_for("operation_subprocess_stdin")
    operation.shutdown()


async def test_async_exit_interrupts_pending_source_without_cancelling_operation():
    client = AsyncStdinClient()
    operation = await ContreeAsyncSession(client, image="base").spawn("cat", stdin_open=True)
    requested = asyncio.Event()
    closed = asyncio.Event()

    async def chunks():
        try:
            requested.set()
            await asyncio.Event().wait()
            yield b"unreachable"
        finally:
            closed.set()

    pipe = asyncio.create_task(operation.pipe_stdin(chunks()))
    await asyncio.wait_for(requested.wait(), 2)
    await client.streams[operation.uuid].put(event("exit"))
    assert await asyncio.wait_for(pipe, 2) == StdinResult(process_exited=True)
    assert closed.is_set()
    assert not client.calls_for("operation_subprocess_stdin")
    assert not client.calls_for("cancel_operation")
    await operation.shutdown()


@pytest.mark.parametrize("failure", [OSError("source failed"), KeyboardInterrupt()])
def test_sync_source_error_or_interrupt_cancels_operation(failure):
    client = StdinClient()
    operation = ContreeSession(client, image="base").spawn("cat", stdin_open=True)

    def chunks():
        yield b"prefix"
        raise failure

    with pytest.raises(type(failure)) as caught:
        operation.pipe_stdin(chunks())
    assert caught.value is failure
    assert len(client.calls_for("cancel_operation")) == 1
    assert not client.calls_for("operation_subprocess_stdin")[-1].kwargs["close"]
    operation.shutdown()


async def test_async_cancellation_cancels_source_and_remote_operation():
    client = AsyncStdinClient()
    operation = await ContreeAsyncSession(client, image="base").spawn("cat", stdin_open=True)
    reading = asyncio.Event()
    closed = asyncio.Event()

    async def chunks():
        try:
            reading.set()
            await asyncio.Event().wait()
            yield b"unreachable"
        finally:
            closed.set()

    pipe = asyncio.create_task(operation.pipe_stdin(chunks()))
    await asyncio.wait_for(reading.wait(), 2)
    pipe.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pipe
    assert closed.is_set()
    assert len(client.calls_for("cancel_operation")) == 1
    await operation.shutdown()


def test_sync_ambiguous_write_is_not_retried():
    client = StdinClient()
    client.write_error = TimeoutError("delivery unknown")
    operation = ContreeSession(client, image="base").spawn("cat", stdin_open=True)
    with pytest.raises(TimeoutError, match="delivery unknown"):
        operation.pipe_stdin([b"once"])
    assert len(client.calls_for("operation_subprocess_stdin")) == 1
    assert len(client.calls_for("cancel_operation")) == 1
    operation.shutdown()


async def test_async_ambiguous_write_is_not_retried():
    client = AsyncStdinClient()
    client.write_error = TimeoutError("delivery unknown")
    operation = await ContreeAsyncSession(client, image="base").spawn("cat", stdin_open=True)
    with pytest.raises(TimeoutError, match="delivery unknown"):
        await operation.pipe_stdin(async_chunks(b"once"))
    assert len(client.calls_for("operation_subprocess_stdin")) == 1
    assert len(client.calls_for("cancel_operation")) == 1
    await operation.shutdown()


def test_sync_delivery_returns_without_waiting_for_operation():
    client = StdinClient()
    client.finish_on_eof = False
    operation = ContreeSession(client, image="base").spawn("cat", stdin_open=True)
    assert operation.pipe_stdin([b"first"], close=False) == StdinResult(5)
    assert operation.pipe_stdin([b"last"]) == StdinResult(4, eof_sent=True)
    assert not client.calls_for("get_operation_status")
    assert not client.calls_for("cancel_operation")
    operation.signal("SIGINT")
    operation.wait(timeout=2)
    operation.shutdown()


async def test_async_delivery_returns_without_waiting_for_operation():
    client = AsyncStdinClient()
    client.finish_on_eof = False
    operation = await ContreeAsyncSession(client, image="base").spawn("cat", stdin_open=True)
    assert await operation.pipe_stdin(async_chunks(b"first"), close=False) == StdinResult(5)
    assert await operation.pipe_stdin(async_chunks(b"last")) == StdinResult(4, eof_sent=True)
    assert not client.calls_for("get_operation_status")
    assert not client.calls_for("cancel_operation")
    await operation.signal("SIGINT")
    await operation.wait(timeout=2)
    await operation.shutdown()


def test_sync_subprocess_keeps_stdin_open():
    client = StdinClient()
    with ContreeSession(client, image="base").spawn("sleep", args=["100"]) as operation:
        handle = operation.run("cat", stdin_open=True)
        assert client.calls_for("operation_subprocess_create")[0].kwargs["stdin"].close is False
        assert operation.pipe_stdin([b"child"], spid=handle.spid).eof_sent
        assert exit_code_of(handle.wait(timeout=2)) == 0
    assert len(client.calls_for("follow_operation_events")) == 1


async def test_async_subprocess_keeps_stdin_open():
    client = AsyncStdinClient()
    async with await ContreeAsyncSession(client, image="base").spawn("sleep", args=["100"]) as operation:
        handle = await operation.run("cat", stdin_open=True)
        assert client.calls_for("operation_subprocess_create")[0].kwargs["stdin"].close is False
        assert (await operation.pipe_stdin(async_chunks(b"child"), spid=handle.spid)).eof_sent
        assert exit_code_of(await handle.wait(timeout=2)) == 0
    assert len(client.calls_for("follow_operation_events")) == 1


def test_sync_exit_during_source_read_discards_the_late_chunk():
    client = StdinClient()
    operation = ContreeSession(client, image="base").spawn("cat", stdin_open=True)

    def chunks():
        yield b"prefix"
        client.streams[operation.uuid].put(event("exit"))
        for item in operation.events():
            if item.type == "exit":
                break
        yield b"too late"
        pytest.fail("source must not be advanced after exit")

    assert operation.pipe_stdin(chunks()) == StdinResult(6, process_exited=True)
    assert bytes(client.received) == b"prefix"
    assert not client.calls_for("operation_subprocess_stdin")[-1].kwargs["close"]
    operation.shutdown()


def test_sync_reader_failure_reaches_input_writer():
    client = StdinClient()
    client.ready = False
    operation = ContreeSession(client, image="base").spawn("cat", stdin_open=True)
    client.streams[operation.uuid].put(OSError("event source failed"))
    with pytest.raises(OSError, match="event source failed"):
        operation.pipe_stdin([b"unused"])
    assert not client.calls_for("operation_subprocess_stdin")
    assert len(client.calls_for("cancel_operation")) == 1
    with pytest.raises(OSError, match="event source failed"):
        operation.shutdown()


async def test_async_reader_failure_interrupts_pending_source():
    client = AsyncStdinClient()
    operation = await ContreeAsyncSession(client, image="base").spawn("cat", stdin_open=True)
    reading = asyncio.Event()

    async def chunks():
        reading.set()
        await asyncio.Event().wait()
        yield b"unused"

    pipe = asyncio.create_task(operation.pipe_stdin(chunks()))
    await asyncio.wait_for(reading.wait(), 2)
    await client.streams[operation.uuid].put(OSError("event source failed"))
    with pytest.raises(OSError, match="event source failed"):
        await asyncio.wait_for(pipe, 2)
    assert not client.calls_for("operation_subprocess_stdin")
    assert len(client.calls_for("cancel_operation")) == 1
    with pytest.raises(OSError, match="event source failed"):
        await operation.shutdown()


async def test_async_source_error_preserves_original_exception():
    client = AsyncStdinClient()
    operation = await ContreeAsyncSession(client, image="base").spawn("cat", stdin_open=True)
    error = OSError("source failed")

    async def chunks():
        yield b"prefix"
        raise error

    with pytest.raises(OSError, match="source failed") as caught:
        await operation.pipe_stdin(chunks())
    assert caught.value is error
    assert len(client.calls_for("cancel_operation")) == 1
    assert not client.calls_for("operation_subprocess_stdin")[-1].kwargs["close"]
    await operation.shutdown()


def test_sync_client_reconnect_keeps_input_and_events_once(monkeypatch):
    from dataclasses import replace

    from contree_client.exceptions import SSEStreamError
    from contree_client.sync import ContreeClient

    client = StdinClient()
    client.ready = False
    client.mock("operation_terminal", False)
    cursors = []
    subscriptions = []

    def stream(operation_id, **kwargs):
        cursors.append(kwargs["last_event_id"])
        if kwargs["last_event_id"] is None:
            yield event("spawn")
            raise SSEStreamError("connection lost", last_event_id=1)
        for index in (2, 3):
            yield replace(client.streams[operation_id].get(timeout=2), id=index)

    def follow(operation_id, **kwargs):
        subscriptions.append(operation_id)
        return ContreeClient.follow_operation_events(client, operation_id, **kwargs)

    monkeypatch.setattr(client, "iter_operation_events", stream)
    monkeypatch.setattr(client, "follow_operation_events", follow)
    operation = ContreeSession(client, image="base").spawn("cat", stdin_open=True)
    assert operation.pipe_stdin([b"only once"]).eof_sent
    operation.wait(timeout=2)
    assert [item.id for item in operation.events()] == [1, 2, 3]
    assert bytes(client.received) == b"only once"
    assert len(client.calls_for("operation_subprocess_stdin")) == 2
    assert cursors == [None, 1]
    assert subscriptions == [operation.uuid]
    operation.shutdown()


async def test_async_client_reconnect_keeps_input_and_events_once(monkeypatch):
    from dataclasses import replace

    from contree_client.asyncio import ContreeAsyncClient
    from contree_client.exceptions import SSEStreamError

    client = AsyncStdinClient()
    client.ready = False
    client.mock("operation_terminal", False)
    cursors = []
    subscriptions = []

    async def stream(operation_id, **kwargs):
        cursors.append(kwargs["last_event_id"])
        if kwargs["last_event_id"] is None:
            yield event("spawn")
            raise SSEStreamError("connection lost", last_event_id=1)
        for index in (2, 3):
            yield replace(await asyncio.wait_for(client.streams[operation_id].get(), 2), id=index)

    def follow(operation_id, **kwargs):
        subscriptions.append(operation_id)
        return ContreeAsyncClient.follow_operation_events(client, operation_id, **kwargs)

    monkeypatch.setattr(client, "iter_operation_events", stream)
    monkeypatch.setattr(client, "follow_operation_events", follow)
    operation = await ContreeAsyncSession(client, image="base").spawn("cat", stdin_open=True)
    assert (await operation.pipe_stdin(async_chunks(b"only once"))).eof_sent
    await operation.wait(timeout=2)
    assert [item.id async for item in operation.events()] == [1, 2, 3]
    assert bytes(client.received) == b"only once"
    assert len(client.calls_for("operation_subprocess_stdin")) == 2
    assert cursors == [None, 1]
    assert subscriptions == [operation.uuid]
    await operation.shutdown()


def test_sync_lazy_session_forwards_open_stdin_to_child():
    from contree_sdk.session import LazySession

    client = StdinClient()
    with LazySession(ContreeSession(client, image="base")) as lazy:
        handle = lazy.spawn("cat", stdin_open=True)
        operation = lazy.operation
        assert operation is not None
        assert client.calls_for("operation_subprocess_create")[0].kwargs["stdin"].close is False
        assert operation.pipe_stdin([b"live"], spid=handle.spid).eof_sent
        assert exit_code_of(handle.wait(timeout=2)) == 0
    assert bytes(client.received) == b"live"
    assert len(client.calls_for("spawn_instance")) == 1
    assert len(client.calls_for("follow_operation_events")) == 1


async def test_async_lazy_session_forwards_open_stdin_to_child():
    from contree_sdk.session import AsyncLazySession

    client = AsyncStdinClient()
    async with AsyncLazySession(ContreeAsyncSession(client, image="base")) as lazy:
        handle = await lazy.spawn("cat", stdin_open=True)
        operation = lazy.operation
        assert operation is not None
        assert client.calls_for("operation_subprocess_create")[0].kwargs["stdin"].close is False
        assert (await operation.pipe_stdin(async_chunks(b"live"), spid=handle.spid)).eof_sent
        assert exit_code_of(await handle.wait(timeout=2)) == 0
    assert bytes(client.received) == b"live"
    assert len(client.calls_for("spawn_instance")) == 1
    assert len(client.calls_for("follow_operation_events")) == 1
