"""Exercise startup against a gated transport and the real shared event reader."""

import asyncio

import pytest
from contree_client.models import FileResponse, OperationStatus

from contree_sdk import AsyncLazySession, ContreeAsyncSession, ContreeSession, LazySession
from contree_sdk.exceptions import FailedOperationError
from contree_sdk.session import CommandCountSnapshotPolicy
from contree_sdk.session.operation_async import AsyncOperation
from contree_sdk.session.operation_sync import Operation
from tests.unit.session.factories import operation_response
from tests.unit.session.lazy_clients import LiveAsyncClient, LiveClient, event


async def invoke(asynchronous, method, *args, **kwargs):
    if asynchronous:
        return await method(*args, **kwargs)
    return await asyncio.to_thread(method, *args, **kwargs)


async def until(predicate):
    async def poll():
        while not predicate():
            await asyncio.sleep(0.001)

    await asyncio.wait_for(poll(), 2)


def make_client(asynchronous):
    client = LiveAsyncClient() if asynchronous else LiveClient()
    client.auto_ready = False
    return client


def make_lazy(base: ContreeAsyncSession | ContreeSession, **kwargs) -> AsyncLazySession | LazySession:
    if isinstance(base, ContreeAsyncSession):
        return AsyncLazySession(base, **kwargs)
    return LazySession(base, **kwargs)


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_operation_waits_for_primary_spawn_with_one_reader(asynchronous):
    client = make_client(asynchronous)
    await invoke(asynchronous, client.spawn_instance, "sleep", "base")
    operation = (AsyncOperation if asynchronous else Operation)(client, "op-1")
    waiters = [asyncio.create_task(invoke(asynchronous, operation.wait_ready, timeout=2)) for _ in range(3)]
    try:
        await until(lambda: client.calls_for("follow_operation_events"))
        client.streams["op-1"].put_nowait(event("init", 0))
        client.streams["op-1"].put_nowait(event("spawn", 2))
        await until(lambda: 2 in operation.spawned)
        assert not any(waiter.done() for waiter in waiters)
        client.streams["op-1"].put_nowait(event("spawn"))
        await asyncio.wait_for(asyncio.gather(*waiters), 2)
        # Repeated calls also use the remembered event, rather than opening a stream.
        await invoke(asynchronous, operation.wait_ready, timeout=2)
        assert len(client.calls_for("follow_operation_events")) == 1
        assert not client.calls_for("operation_subprocess_create")
        assert not client.calls_for("get_operation_status")
    finally:
        await invoke(asynchronous, operation.cancel)
        await invoke(asynchronous, operation.shutdown)


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("ending", [None, event("completion"), event("exit"), OSError("stream lost")])
async def test_operation_startup_failure_reports_operation_and_backend_error(asynchronous, ending, monkeypatch):
    client = make_client(asynchronous)
    await invoke(asynchronous, client.spawn_instance, "sleep", "base")
    response = operation_response(status=OperationStatus.FAILED, error="guest boot failed", with_result=False)

    async def async_status(*args, **kwargs):
        return response

    monkeypatch.setattr(client, "get_operation_status", async_status if asynchronous else lambda *a, **kw: response)
    operation = (AsyncOperation if asynchronous else Operation)(client, "op-1")
    client.streams["op-1"].put_nowait(ending)
    try:
        with pytest.raises(FailedOperationError, match=r"op-1.*guest boot failed"):
            await invoke(asynchronous, operation.wait_ready, timeout=2)
        assert operation.response is response
        assert not client.calls_for("operation_subprocess_create")
    finally:
        if isinstance(ending, OSError):
            with pytest.raises(OSError, match="stream lost"):
                await invoke(asynchronous, operation.shutdown)
        else:
            await invoke(asynchronous, operation.shutdown)


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_readiness_timeout_leaves_shared_reader_available(asynchronous):
    client = make_client(asynchronous)
    await invoke(asynchronous, client.spawn_instance, "sleep", "base")
    operation = (AsyncOperation if asynchronous else Operation)(client, "op-1")
    try:
        with pytest.raises(TimeoutError, match=r"op-1.*startup timed out"):
            await invoke(asynchronous, operation.wait_ready, timeout=0.01)
        assert not operation.terminal
        assert not client.calls_for("cancel_operation")
        client.streams["op-1"].put_nowait(event("spawn"))
        await invoke(asynchronous, operation.wait_ready, timeout=2)
        assert len(client.calls_for("follow_operation_events")) == 1
    finally:
        await invoke(asynchronous, operation.cancel)
        await invoke(asynchronous, operation.shutdown)


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_lazy_waits_for_each_vm_before_admitting_commands(asynchronous):
    client = make_client(asynchronous)
    base = ContreeAsyncSession(client, image="base") if asynchronous else ContreeSession(client, image="base")
    lazy = make_lazy(base, startup_timeout=2)
    try:
        for index in (1, 2):
            running = asyncio.create_task(invoke(asynchronous, lazy.run, "first"))
            operation_id = f"op-{index}"
            await until(lambda operation_id=operation_id: operation_id in client.streams)
            assert lazy.phase == "starting"
            before = len(client.calls_for("operation_subprocess_create"))
            concurrent = asyncio.create_task(invoke(asynchronous, lazy.run, "second"))
            await until(
                lambda concurrent=concurrent: client.calls_for("follow_operation_events") and not concurrent.done()
            )
            assert len(client.calls_for("operation_subprocess_create")) == before
            client.streams[operation_id].put_nowait(event("spawn"))
            await asyncio.wait_for(asyncio.gather(running, concurrent), 2)
            assert len(client.calls_for("operation_subprocess_create")) == before + 2
            await invoke(asynchronous, lazy.snapshot, timeout=2)
        assert len(client.calls_for("follow_operation_events")) == 2
    finally:
        await invoke(asynchronous, lazy.abort)


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_lazy_startup_timeout_cancels_vm_without_submitting_command(asynchronous):
    client = make_client(asynchronous)
    base = ContreeAsyncSession(client, image="base") if asynchronous else ContreeSession(client, image="base")
    lazy = make_lazy(base, startup_timeout=0.02)
    try:
        with pytest.raises(TimeoutError, match=r"op-1.*startup timed out"):
            await invoke(asynchronous, lazy.run, "must not run")
        assert lazy.phase == "failed"
        assert not client.calls_for("operation_subprocess_create")
        await until(lambda: client.calls_for("cancel_operation"))
    finally:
        await invoke(asynchronous, lazy.abort)


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_abort_during_startup_releases_waiter_and_worker(asynchronous):
    client = make_client(asynchronous)
    base = ContreeAsyncSession(client, image="base") if asynchronous else ContreeSession(client, image="base")
    lazy = make_lazy(base, startup_timeout=2)
    running = asyncio.create_task(invoke(asynchronous, lazy.run, "must not run"))
    await until(lambda: lazy.phase == "starting" and "op-1" in client.streams)
    await asyncio.wait_for(invoke(asynchronous, lazy.abort), 2)
    with pytest.raises(RuntimeError, match="closed"):
        await running
    assert lazy.phase == "closed"
    assert not client.calls_for("operation_subprocess_create")


async def test_cancelling_readiness_wait_does_not_cancel_reader():
    client = make_client(True)
    await client.spawn_instance("sleep", "base")
    operation = AsyncOperation(client, "op-1")
    waiting = asyncio.create_task(operation.wait_ready())
    try:
        await until(lambda: client.calls_for("follow_operation_events"))
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        assert not operation.terminal
        assert not client.calls_for("cancel_operation")
        client.streams["op-1"].put_nowait(event("spawn"))
        await operation.wait_ready(timeout=2)
    finally:
        await operation.cancel()
        await operation.shutdown()


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_snapshot_requested_during_startup_is_not_lost(asynchronous):
    client = make_client(asynchronous)
    base = ContreeAsyncSession(client, image="base") if asynchronous else ContreeSession(client, image="base")
    lazy = make_lazy(base, startup_timeout=2)
    running = asyncio.create_task(invoke(asynchronous, lazy.run, "first"))
    try:
        await until(lambda: lazy.phase == "starting" and "op-1" in client.streams)
        saving = asyncio.create_task(invoke(asynchronous, lazy.snapshot, timeout=2))
        await until(lambda: lazy.state.snapshot_pending)
        client.streams["op-1"].put_nowait(event("spawn"))
        saved = await asyncio.wait_for(saving, 2)
        assert saved.image_uuid == "image-op-1"
        await until(lambda: "op-2" in client.streams)
        assert not client.calls_for("operation_subprocess_create")
        client.streams["op-2"].put_nowait(event("spawn"))
        await asyncio.wait_for(running, 2)
    finally:
        await invoke(asynchronous, lazy.abort)


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_live_upload_also_waits_for_primary_spawn(asynchronous):
    client = make_client(asynchronous)
    client.mock("ensure_file", FileResponse(uuid="uploaded", sha256="a" * 64, size=4))
    client.mock("apply_instance_file", None)
    base = ContreeAsyncSession(client, image="base") if asynchronous else ContreeSession(client, image="base")
    lazy = make_lazy(base, startup_timeout=2)
    writing = asyncio.create_task(invoke(asynchronous, lazy.write_file, "/input", b"data"))
    try:
        await until(lambda: client.calls_for("follow_operation_events"))
        assert lazy.phase == "starting"
        assert not client.calls_for("apply_instance_file")
        client.streams["op-1"].put_nowait(event("spawn"))
        await asyncio.wait_for(writing, 2)
        assert len(client.calls_for("apply_instance_file")) == 1
        assert not client.calls_for("operation_subprocess_create")
    finally:
        await invoke(asynchronous, lazy.abort)


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_concurrent_startup_preserves_one_command_snapshot_limit(asynchronous):
    client = make_client(asynchronous)
    base = ContreeAsyncSession(client, image="base") if asynchronous else ContreeSession(client, image="base")
    lazy = make_lazy(base, startup_timeout=2, snapshot_policy=CommandCountSnapshotPolicy(1))
    first = asyncio.create_task(invoke(asynchronous, lazy.run, "first"))
    try:
        await until(lambda: "op-1" in client.streams)
        second = asyncio.create_task(invoke(asynchronous, lazy.run, "second"))
        client.streams["op-1"].put_nowait(event("spawn"))
        await until(lambda: "op-2" in client.streams)
        assert [call.args for call in client.calls_for("operation_subprocess_create")] == [("op-1", "first")]
        client.streams["op-2"].put_nowait(event("spawn"))
        await asyncio.wait_for(asyncio.gather(first, second), 2)
        assert [call.args for call in client.calls_for("operation_subprocess_create")] == [
            ("op-1", "first"),
            ("op-2", "second"),
        ]
    finally:
        await invoke(asynchronous, lazy.abort)


async def test_cancelled_starting_command_cleans_up_vm():
    client = make_client(True)
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"), startup_timeout=2)
    running = asyncio.create_task(lazy.run("must not run"))
    try:
        await until(lambda: client.calls_for("follow_operation_events"))
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        assert client.calls_for("cancel_operation")
        assert not client.calls_for("operation_subprocess_create")
        assert lazy.phase == "failed"
    finally:
        await lazy.abort()


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_close_during_startup_saves_vm_without_admitting_command(asynchronous):
    client = make_client(asynchronous)
    base = ContreeAsyncSession(client, image="base") if asynchronous else ContreeSession(client, image="base")
    lazy = make_lazy(base, startup_timeout=2)
    running = asyncio.create_task(invoke(asynchronous, lazy.run, "must not run"))
    try:
        await until(lambda: "op-1" in client.streams)
        closing = asyncio.create_task(invoke(asynchronous, lazy.close, timeout=2))
        await until(lambda: lazy.state.closing)
        client.streams["op-1"].put_nowait(event("spawn"))
        await asyncio.wait_for(closing, 2)
        with pytest.raises(RuntimeError, match="closed"):
            await running
        assert lazy.phase == "closed"
        assert lazy.last_entry is not None
        assert lazy.last_entry.image_uuid == "image-op-1"
        assert not client.calls_for("operation_subprocess_create")
    finally:
        await invoke(asynchronous, lazy.abort)
