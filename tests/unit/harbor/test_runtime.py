"""Fixed lifetime uses the real LazySession lifecycle and one Operation reader."""

import asyncio

import pytest
from contree_client.models import InstanceNetworking, InstanceResourcesLimits, StreamRepr

from contree_sdk import ContreeAsyncSession, RunRequest
from contree_sdk.harbor.runtime import ContreeAsyncRuntime, RuntimeOptions
from tests.unit.session.lazy_clients import LiveAsyncClient, event


def make_runtime(client=None, **kwargs):
    client = client if client is not None else LiveAsyncClient()
    session = ContreeAsyncSession(client, image="base")
    return client, session, ContreeAsyncRuntime(session, options=RuntimeOptions(**kwargs))


async def test_fixed_lifetime_is_explicit_and_reuses_one_operation():
    client, session, runtime = make_runtime()
    async with runtime:
        assert not client.calls_for("spawn_instance")
        await runtime.start()
        await runtime.start()
        assert not client.calls_for("operation_subprocess_create")
        assert (await runtime.run("first")).stdout == StreamRepr.from_text("first")
        assert (await runtime.run("second")).stdout == StreamRepr.from_text("second")
        assert runtime.operation_uuid == "op-1"
        assert len(client.calls_for("spawn_instance")) == 1
        assert len(client.calls_for("follow_operation_events")) == 1
        assert not runtime.lifecycle.snapshot_policy.should_snapshot().done()
        assert len((await session.history())[0]) == 1
    assert await runtime.stop() is None
    assert len(client.calls_for("cancel_operation")) == 1
    assert runtime.lifecycle.worker.done()
    assert runtime.lifecycle.operation.consumer_task.done()
    with pytest.raises(RuntimeError, match="stopped"):
        await runtime.run("third")


async def test_command_identity_and_vm_resources_use_public_client_fields():
    vm = RunRequest(
        command="sleep",
        args=("100",),
        disposable=False,
        uid=1,
        gid=2,
        resources_limits=InstanceResourcesLimits(max_layer_bytes=1024),
        networking=InstanceNetworking(enabled=False),
        hostname="runtime",
    )
    client, _, runtime = make_runtime(vm_request=vm)
    async with runtime:
        await runtime.run(shell="id", cwd="/work", env={"X": "yes"}, uid=12, gid=34)
        startup = client.calls_for("spawn_instance")[0].kwargs
        assert (startup["uid"], startup["gid"], startup["hostname"]) == (1, 2, "runtime")
        assert startup["resources_limits"].max_layer_bytes == 1024
        assert startup["networking"].enabled is False
        command = client.calls_for("operation_subprocess_create")[0].kwargs
        assert (command["uid"], command["gid"], command["cwd"], command["env"]) == (12, 34, "/work", {"X": "yes"})
        assert command["shell"] is True


async def test_snapshot_is_confirmed_and_nonzero_commands_do_not_prevent_it():
    client, session, runtime = make_runtime()
    client.exit_code = 7
    assert (await runtime.run("false")).state.exit_code == 7
    entry = await runtime.stop(snapshot=True)
    assert entry.image_uuid == "image-op-1"
    assert session.image_uuid == entry.image_uuid
    assert await runtime.stop(snapshot=True) == entry
    assert len((await session.history())[0]) == 2
    assert not client.calls_for("cancel_operation")


async def test_missing_snapshot_image_does_not_advance_history():
    client, session, runtime = make_runtime()
    client.result_image = False
    await runtime.run("first")
    with pytest.raises(RuntimeError, match="could not save"):
        await runtime.stop(snapshot=True)
    assert session.image_uuid == "base"
    assert len((await session.history())[0]) == 1
    assert runtime.error is not None
    assert runtime.lifecycle.worker.done()


@pytest.mark.parametrize("cancel", [False, True])
async def test_command_timeout_or_cancellation_preserves_sibling(cancel):
    client, _, runtime = make_runtime(terminate_timeout=0.2)
    client.auto_exit = False
    try:
        first = asyncio.create_task(runtime.run("first", timeout=None if cancel else 0.03))
        await client.created.wait()
        sibling = await runtime.spawn_request(RunRequest(command="sibling", disposable=False))
        if cancel:
            first.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TimeoutError):
            await first
        assert client.calls_for("operation_subprocess_kill")[-1].args == ("op-1", 2)
        assert not client.calls_for("cancel_operation")
        assert runtime.error is None
        await client.streams["op-1"].put(event("exit", sibling.spid))
        assert (await sibling.wait(timeout=1)).stdout == StreamRepr.from_text("sibling")
        client.auto_exit = True
        assert (await runtime.run("third")).stdout == StreamRepr.from_text("third")
        assert len(client.calls_for("spawn_instance")) == 1
    finally:
        await runtime.stop()


async def test_final_result_rpc_is_included_in_command_timeout(monkeypatch):
    client, _, runtime = make_runtime()
    gate = asyncio.Event()
    original = client.operation_subprocess

    async def result(operation, spid):
        if spid == 2:
            await gate.wait()
        return await original(operation, spid)

    monkeypatch.setattr(client, "operation_subprocess", result)
    try:
        with pytest.raises(TimeoutError):
            await runtime.run("first", timeout=0.02)
        assert not client.calls_for("cancel_operation")
        assert not client.calls_for("operation_subprocess_kill")
        assert (await runtime.run("second")).stdout == StreamRepr.from_text("second")
    finally:
        gate.set()
        await runtime.stop()


async def test_unconfirmed_kill_fails_runtime_and_cancels_vm(monkeypatch):
    client, _, runtime = make_runtime(terminate_timeout=0.02)
    client.auto_exit = False
    original = client.operation_subprocess_kill

    async def ignore_child(operation, spid, **kwargs):
        if spid == 1:
            await original(operation, spid, **kwargs)
        else:
            client.record_call("operation_subprocess_kill", (operation, spid), kwargs)

    monkeypatch.setattr(client, "operation_subprocess_kill", ignore_child)
    with pytest.raises(TimeoutError):
        await runtime.run("first", timeout=0.02)
    assert isinstance(runtime.error, TimeoutError)
    assert client.calls_for("cancel_operation")
    assert runtime.lifecycle.worker.done()
    with pytest.raises(RuntimeError, match="stopped"):
        await runtime.run("second")


async def test_cancelled_start_waits_for_uuid_and_releases_vm(monkeypatch):
    client, _, runtime = make_runtime()
    entered, release = asyncio.Event(), asyncio.Event()
    original = client.spawn_instance

    async def spawn(command, image, **kwargs):
        entered.set()
        await release.wait()
        return await original(command, image, **kwargs)

    monkeypatch.setattr(client, "spawn_instance", spawn)
    start = asyncio.create_task(runtime.start())
    await entered.wait()
    start.cancel()
    await asyncio.sleep(0)
    assert not start.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(start, 1)
    assert client.calls_for("cancel_operation")[0].args == ("op-1",)
    assert runtime.lifecycle.worker.done()
    assert runtime.lifecycle.operation.consumer_task.done()


async def test_cancelled_stop_finishes_snapshot_and_is_idempotent():
    client, session, runtime = make_runtime()
    client.wait_gate = asyncio.Event()
    await runtime.run("first")
    stop = asyncio.create_task(runtime.stop(snapshot=True))
    await client.saving.wait()
    stop.cancel()
    await asyncio.sleep(0)
    assert not stop.done()
    client.wait_gate.set()
    with pytest.raises(asyncio.CancelledError):
        await stop
    entry = await runtime.stop(snapshot=True)
    assert entry.image_uuid == session.image_uuid == "image-op-1"
    assert runtime.lifecycle.worker.done()


async def test_timeout_can_terminate_command_while_snapshot_is_draining():
    client, session, runtime = make_runtime(stop_timeout=1)
    client.auto_exit = False
    command = asyncio.create_task(runtime.run("first", timeout=0.03))
    await client.created.wait()
    stop = asyncio.create_task(runtime.stop(snapshot=True))
    with pytest.raises(TimeoutError):
        await command
    entry = await stop
    assert entry.image_uuid == session.image_uuid == "image-op-1"
    assert not client.calls_for("cancel_operation")


async def test_failed_stdin_only_stops_target_process():
    client, _, runtime = make_runtime()
    client.auto_exit = False
    client.mock("operation_subprocess_stdin", None)
    try:
        handle = await runtime.spawn_request(RunRequest(command="cat", disposable=False, stdin_open=True))
        sibling = await runtime.spawn_request(RunRequest(command="other", disposable=False))
        await client.streams["op-1"].put(event("spawn", handle.spid))

        async def chunks():
            yield b"input"
            raise OSError("input failed")

        with pytest.raises(OSError, match="input failed"):
            await runtime.pipe_stdin(chunks(), spid=handle.spid)
        assert not client.calls_for("cancel_operation")
        assert all(call.args[1] == handle.spid for call in client.calls_for("operation_subprocess_kill"))
        assert client.calls_for("operation_subprocess_stdin")[0].args[:2] == ("op-1", handle.spid)
        await client.streams["op-1"].put(event("exit", sibling.spid))
        await sibling.wait(timeout=1)
    finally:
        await runtime.stop()


async def test_vm_loss_fails_commands_without_restarting():
    client, session, runtime = make_runtime()
    client.auto_exit = False
    command = asyncio.create_task(runtime.run("first"))
    await client.created.wait()
    await client.streams["op-1"].put(event("exit", 1))
    with pytest.raises(RuntimeError):
        await command
    assert runtime.error is not None
    assert len((await session.history())[0]) == 1
    await runtime.stop()
    assert len(client.calls_for("spawn_instance")) == 1


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
async def test_invalid_command_timeout_does_not_start_vm(timeout):
    client, _, runtime = make_runtime()
    with pytest.raises(ValueError, match="timeout"):
        await runtime.run("first", timeout=timeout)
    assert not client.calls_for("spawn_instance")
    await runtime.stop()


async def test_cancel_during_subprocess_creation_fails_uncertain_vm():
    client, _, runtime = make_runtime()
    client.create_gate = asyncio.Event()
    try:
        with pytest.raises(TimeoutError):
            await runtime.run("unknown", timeout=0.02)
        assert runtime.error is not None
        assert client.calls_for("cancel_operation")
        with pytest.raises(RuntimeError):
            await runtime.run("next")
    finally:
        client.create_gate.set()
        await runtime.stop()


async def test_partial_start_failure_releases_the_known_operation(monkeypatch):
    client, _, runtime = make_runtime()
    original = runtime.lifecycle.session.create_operation

    def operation(response, context):
        handle = original(response, context)
        handle.shutdown_timeout = 0.01

        def register(observer):
            raise RuntimeError("observer setup")

        monkeypatch.setattr(handle, "add_observer", register)
        return handle

    monkeypatch.setattr(runtime.lifecycle.session, "create_operation", operation)
    with pytest.raises(RuntimeError, match="observer setup"):
        await runtime.start()
    assert client.calls_for("cancel_operation")
    assert runtime.lifecycle.operation.consumer_task is None
    assert runtime.lifecycle.worker is None
    await runtime.stop()


async def test_factory_can_return_an_independent_runtime():
    from contree_client.models import InstanceResult

    from contree_sdk.harbor.runtime import AsyncRuntime, create_runtime

    result = InstanceResult(stdout=StreamRepr.from_text("independent"))

    class IndependentRuntime(AsyncRuntime):
        operation_uuid = "independent"
        error = None

        async def start(self):
            pass

        async def spawn_request(self, request):
            raise NotImplementedError

        async def execute(self, request):
            return result

        async def terminate(self, spid):
            pass

        async def send_stdin(self, data, *, spid, close=True):
            pass

        async def pipe_stdin(self, chunks, *, spid, close=True, chunk_size=65536):
            raise NotImplementedError

        def events(self, *, spid=None, timeout=None):
            raise NotImplementedError

        async def stop(self, *, snapshot=False):
            return None

    expected = IndependentRuntime()
    received = []

    def factory(session, *, options=None):
        received.append((session, options))
        return expected

    client = LiveAsyncClient()
    session = ContreeAsyncSession(client, image="base")
    options = RuntimeOptions()
    runtime = create_runtime(session, options=options, factory=factory)
    assert runtime is expected
    assert await runtime.run("unused") == result
    assert received == [(session, options)]
    assert not client.calls_for("spawn_instance")


def test_sync_session_and_lazy_process_identity_are_consistent():
    from contree_sdk import ContreeSession, LazySession
    from contree_sdk.session import Operation
    from tests.unit.session.lazy_clients import LiveClient

    client = LiveClient()
    session = ContreeSession(client, image="base")
    operation = session.spawn("true", uid=12, gid=34, networking=InstanceNetworking(enabled=False))
    assert client.calls_for("spawn_instance")[0].kwargs["uid"] == 12
    assert client.calls_for("spawn_instance")[0].kwargs["gid"] == 34
    assert client.calls_for("spawn_instance")[0].kwargs["networking"].enabled is False
    assert isinstance(operation, Operation)
    operation.shutdown_timeout = 0.01
    operation.cancel()
    operation.shutdown()
    with LazySession(session) as lazy:
        lazy.run("id", uid=56, gid=78)
        call = client.calls_for("operation_subprocess_create")[0]
        assert (call.kwargs["uid"], call.kwargs["gid"]) == (56, 78)


async def test_startup_lookup_failure_is_available_as_runtime_error():
    client, _, runtime = make_runtime()
    client.mocks["resolve_image"].clear()
    error = RuntimeError("image lookup failed")
    client.mock("resolve_image", error=error)
    with pytest.raises(RuntimeError, match="image lookup failed"):
        await runtime.start()
    assert runtime.error is error
    assert not client.calls_for("spawn_instance")
    await runtime.stop()


async def test_results_and_events_are_separate_for_each_subprocess():
    from contree_client.models import InstanceResult, InstanceResultState

    client, _, runtime = make_runtime()
    client.auto_exit = False
    client.mock("operation_subprocess_stdin", None)
    try:
        one = await runtime.spawn_request(RunRequest(command="one", disposable=False, stdin_open=True))
        two = await runtime.spawn_request(RunRequest(command="two", disposable=False, stdin_open=True))
        client.results["op-1", one.spid] = InstanceResult(
            state=InstanceResultState(exit_code=3),
            stdout=StreamRepr.from_text("first out"),
            stderr=StreamRepr.from_text("first err"),
        )
        await runtime.send_stdin(b"first", spid=one.spid, close=False)
        await runtime.send_stdin(b"second", spid=two.spid)
        await client.streams["op-1"].put(event("exit", two.spid))
        await client.streams["op-1"].put(event("exit", one.spid))
        first, second = await asyncio.gather(one.wait(timeout=1), two.wait(timeout=1))
        assert first.state.exit_code == 3
        assert first.stdout == StreamRepr.from_text("first out")
        assert first.stderr == StreamRepr.from_text("first err")
        assert second.stdout == StreamRepr.from_text("two")
        subscription = runtime.events(spid=one.spid)
        try:
            assert (await anext(subscription)).spid == one.spid
        finally:
            await subscription.aclose()
        assert len(client.calls_for("follow_operation_events")) == 1
        calls = client.calls_for("operation_subprocess_stdin")
        assert [call.args[1] for call in calls] == [one.spid, two.spid]
    finally:
        await runtime.stop()
