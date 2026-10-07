import asyncio

import pytest
from contree_client.models import InstanceResultState, OperationStatus, StreamRepr

from contree_sdk import AsyncLazySession, ContreeAsyncSession
from contree_sdk.session import AbstractSnapshotPolicy, CommandCountSnapshotPolicy, IdleSnapshotPolicy
from tests.unit.session.lazy_clients import LiveAsyncClient, event
from tests.unit.session.timers import ManualTimers


async def wait_state(lazy, predicate):
    async with lazy.condition:
        await asyncio.wait_for(lazy.condition.wait_for(predicate), 2)


async def test_shared_vm_snapshot_and_next_image():
    client = LiveAsyncClient()
    base = ContreeAsyncSession(client, image="base")
    async with AsyncLazySession(base) as lazy:
        assert not client.calls_for("spawn_instance")
        assert (await lazy.run("first")).stdout == StreamRepr.from_text("first")
        assert (await lazy.run("second")).stdout == StreamRepr.from_text("second")
        assert len(client.calls_for("spawn_instance")) == 1
        assert len(client.calls_for("follow_operation_events")) == 1
        assert len((await base.history())[0]) == 1
        entry = await lazy.snapshot(timeout=2)
        assert entry is not None
        assert entry.image_uuid == "image-op-1"
        await lazy.run("third")
        assert client.calls_for("spawn_instance")[1].args[1] == "image-op-1"
    assert lazy.phase == "closed"
    assert lazy.worker is not None
    assert lazy.worker.done()
    assert len((await base.history())[0]) == 3


async def test_idle_timer_waits_for_exit_without_user_wait():
    client = LiveAsyncClient()
    client.auto_exit = False
    timers = ManualTimers()
    lazy = AsyncLazySession(
        ContreeAsyncSession(client, image="base"), snapshot_policy=IdleSnapshotPolicy(5, timer_factory=timers.start)
    )
    try:
        handle = await lazy.spawn("long")
        timers.advance(100)
        assert not client.calls_for("operation_subprocess_kill")
        await client.streams["op-1"].put(event("exit", handle.spid))
        await wait_state(lazy, lambda: not lazy.state.active)
        timers.advance(5)
        await wait_state(lazy, lambda: lazy.phase == "cold")
    finally:
        await lazy.abort()


async def test_parallel_commands_reserve_exact_count_and_wait_for_snapshot():
    client = LiveAsyncClient()
    client.wait_gate = asyncio.Event()
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"), snapshot_policy=CommandCountSnapshotPolicy(2))
    try:
        await asyncio.wait_for(asyncio.gather(lazy.run("one"), lazy.run("two")), 2)
        await asyncio.wait_for(client.saving.wait(), 2)
        three = asyncio.create_task(lazy.run("three"))
        await asyncio.sleep(0)
        assert len(client.calls_for("operation_subprocess_create")) == 2
        client.wait_gate.set()
        await asyncio.wait_for(three, 2)
        assert [call.args[0] for call in client.calls_for("operation_subprocess_create")] == ["op-1", "op-1", "op-2"]
    finally:
        client.wait_gate.set()
        await lazy.close(timeout=2)


@pytest.mark.parametrize("failure", [OSError("stream broken"), None, event("exit", 1)])
async def test_unexpected_stream_end_does_not_claim_snapshot(failure):
    client = LiveAsyncClient()
    client.auto_exit = False
    base = ContreeAsyncSession(client, image="base")
    lazy = AsyncLazySession(base)
    await lazy.spawn("long")
    await client.streams["op-1"].put(failure)
    await wait_state(lazy, lambda: lazy.error is not None)
    with pytest.raises(RuntimeError):
        await lazy.snapshot(timeout=2)
    assert len((await base.history())[0]) == 1
    await lazy.abort()
    assert lazy.worker is not None
    assert lazy.worker.done()


@pytest.mark.parametrize("missing_image", [False, True])
async def test_snapshot_failure_preserves_history(missing_image):
    client = LiveAsyncClient()
    client.result_image = not missing_image
    if not missing_image:
        client.wait_error = OSError("wait failed")
    base = ContreeAsyncSession(client, image="base")
    lazy = AsyncLazySession(base)
    await lazy.run("one")
    with pytest.raises(RuntimeError):
        await lazy.snapshot(timeout=2)
    assert base.image_uuid == "base"
    assert len((await base.history())[0]) == 1
    await lazy.abort()


async def test_nonzero_result_creation_error_and_navigation():
    client = LiveAsyncClient()
    client.exit_code = 3
    base = ContreeAsyncSession(client, image="base")
    lazy = AsyncLazySession(base)
    assert (await lazy.run("false")).state == InstanceResultState(exit_code=3)
    with pytest.raises(RuntimeError, match="snapshot"):
        await lazy.rollback()
    with pytest.raises(ValueError, match="disposable"):
        await lazy.run("echo", disposable=True)
    await lazy.snapshot(timeout=2)
    await lazy.create_branch("experiment")
    await lazy.switch_branch("experiment")
    client.create_error = OSError("create failed")
    with pytest.raises(OSError):
        await lazy.spawn("broken")
    with pytest.raises(RuntimeError):
        await lazy.close(timeout=2)
    assert lazy.phase == "closed"


async def test_timeout_kills_only_the_subprocess():
    client = LiveAsyncClient()
    client.auto_exit = False
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"))
    try:
        with pytest.raises(TimeoutError):
            await lazy.run("long", timeout=0.01)
        assert client.calls_for("operation_subprocess_kill")[0].args == ("op-1", 2)
    finally:
        await lazy.close(timeout=2)


async def test_cancelled_create_fails_epoch_without_claiming_no_active_processes():
    client = LiveAsyncClient()
    client.create_gate = asyncio.Event()
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"))
    task = asyncio.create_task(lazy.spawn("ambiguous"))
    await asyncio.wait_for(client.created.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert lazy.phase == "failed"
    with pytest.raises(RuntimeError):
        await lazy.spawn("next")
    await lazy.abort()
    assert len(client.calls_for("cancel_operation")) >= 1


async def test_snapshot_conflict_keeps_response_for_recovery():
    client = LiveAsyncClient()
    base = ContreeAsyncSession(client, image="base")
    lazy = AsyncLazySession(base)
    await lazy.run("one")
    await base.store.append(base.session_id, image_uuid="external", parent_id=base.tip_id)
    with pytest.raises(RuntimeError):
        await lazy.snapshot(timeout=2)
    from contree_sdk.exceptions import SessionConflictError

    assert isinstance(lazy.error, SessionConflictError)
    assert lazy.operation is not None
    assert lazy.operation.response is not None
    assert lazy.operation.response.result_image_uuid == "image-op-1"
    tip = await base.store.tip(base.session_id)
    assert tip is not None
    assert tip.image_uuid == "external"
    await lazy.abort()


async def test_pending_create_excludes_timer_and_close_until_admission_finishes():
    client = LiveAsyncClient()
    client.create_gate = asyncio.Event()
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"), snapshot_policy=CommandCountSnapshotPolicy(1))
    command = asyncio.create_task(lazy.run("one"))
    await asyncio.wait_for(client.created.wait(), 2)
    closing = asyncio.create_task(lazy.close(timeout=2))
    await asyncio.sleep(0)
    assert not client.calls_for("operation_subprocess_kill")
    client.create_gate.set()
    await asyncio.wait_for(asyncio.gather(command, closing), 2)
    assert len(client.calls_for("follow_operation_events")) == 1
    assert not client.calls_for("wait_operation")


async def test_eof_reaches_handle_wait_instead_of_returning_a_synthetic_result():
    client = LiveAsyncClient()
    client.auto_exit = False
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"))
    handle = await lazy.spawn("long")
    await client.streams["op-1"].put(None)
    with pytest.raises(RuntimeError, match="completion"):
        await handle.wait(timeout=2)
    await lazy.abort()


async def test_cancelled_snapshot_wait_keeps_worker_and_active_command_alive():
    client = LiveAsyncClient()
    client.auto_exit = False
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"))
    handle = await lazy.spawn("long")
    waiting = asyncio.create_task(lazy.snapshot())
    await wait_state(lazy, lambda: lazy.phase == "draining")
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    assert not client.calls_for("operation_subprocess_kill")
    await client.streams["op-1"].put(event("exit", handle.spid))
    await lazy.close(timeout=2)
    assert lazy.worker is not None
    assert lazy.worker.done()


async def test_cold_close_and_context_exception_release_resources():
    client = LiveAsyncClient()
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"))
    async with lazy:
        assert await lazy.snapshot() is None
    await lazy.close()
    await lazy.close()
    assert not client.calls_for("spawn_instance")
    with pytest.raises(ValueError, match="application"):  # noqa: PT012 - exercise exceptional context exit
        async with AsyncLazySession(ContreeAsyncSession(client, image="base")) as lazy:
            await lazy.run("one")
            raise ValueError("application")
    assert client.calls_for("cancel_operation")
    assert not client.calls_for("get_operation_status")


async def test_idle_deadline_during_startup_still_admits_first_command():
    timers = ManualTimers()

    class SlowStartClient(LiveAsyncClient):
        async def spawn_instance(self, command, image, **kwargs):
            response = await super().spawn_instance(command, image, **kwargs)
            timers.advance(100)
            return response

    client = SlowStartClient()
    async with AsyncLazySession(
        ContreeAsyncSession(client, image="base"), snapshot_policy=IdleSnapshotPolicy(5, timer_factory=timers.start)
    ) as lazy:
        await lazy.run("first")
        assert len(client.calls_for("spawn_instance")) == 1
        assert len(client.calls_for("operation_subprocess_create")) == 1


@pytest.mark.parametrize("status", [OperationStatus.FAILED, OperationStatus.CANCELLED])
async def test_unsuccessful_snapshot_never_advances_history(status):
    client = LiveAsyncClient()
    client.final_status = status
    base = ContreeAsyncSession(client, image="base")
    lazy = AsyncLazySession(base)
    await lazy.run("one")
    with pytest.raises(RuntimeError, match="snapshot"):
        await lazy.snapshot(timeout=2)
    assert base.image_uuid == "base"
    assert len((await base.history())[0]) == 1
    await lazy.abort()


async def test_custom_future_wakes_controller_but_does_not_stop_active_command():
    class ManualPolicy(AbstractSnapshotPolicy):
        def notify(self, event):
            super().notify(event)

    client = LiveAsyncClient()
    client.auto_exit = False
    policy = ManualPolicy()
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"), snapshot_policy=policy)
    handle = await lazy.spawn("long")
    policy.future.set_result(None)
    await wait_state(lazy, lambda: lazy.phase == "draining")
    assert not client.calls_for("operation_subprocess_kill")
    await client.streams["op-1"].put(event("exit", handle.spid))
    await wait_state(lazy, lambda: lazy.phase == "cold")
    await lazy.close(timeout=2)


async def test_policy_future_failure_wakes_controller_and_preserves_error():
    class FailingPolicy(AbstractSnapshotPolicy):
        def notify(self, event):
            super().notify(event)

    client = LiveAsyncClient()
    policy = FailingPolicy()
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"), snapshot_policy=policy)
    await lazy.run("one")
    error = ValueError("policy decision failed")
    policy.future.set_exception(error)
    await wait_state(lazy, lambda: lazy.phase == "failed")
    assert lazy.error is error
    await lazy.abort()


async def test_staged_files_are_consumed_only_when_lazy_vm_is_snapshotted():
    from contree_sdk.files import UploadedFile, UploadFileSpec

    client = LiveAsyncClient()
    base = ContreeAsyncSession(client, image="base")
    staged = await base.stage_files({"/input": UploadFileSpec(source=UploadedFile("upload", "a" * 64))})
    async with AsyncLazySession(base) as lazy:
        await lazy.run("cat /input")
        assert await base.pending_files() == staged.attachments
        assert client.calls_for("spawn_instance")[0].kwargs["files"]["/input"].uuid == "upload"
        await lazy.snapshot(timeout=2)
        assert await base.pending_files() == ()
    await base.rollback()
    assert await base.pending_files() == staged.attachments


async def test_rejected_snapshot_does_not_restart_from_stale_image():
    from contree_sdk.session import AbstractCommitPolicy

    class RejectSnapshot(AbstractCommitPolicy):
        def should_commit(self, context, result):
            return False

    client = LiveAsyncClient()
    base = ContreeAsyncSession(client, image="base", commit_policy=RejectSnapshot())
    lazy = AsyncLazySession(base)
    await lazy.run("write")
    try:
        with pytest.raises(RuntimeError):
            await lazy.snapshot(timeout=2)
        assert lazy.last_entry is None
        assert base.image_uuid == "base"
        assert len((await base.history())[0]) == 1
        with pytest.raises(RuntimeError):
            await lazy.run("read")
        assert len(client.calls_for("spawn_instance")) == 1
    finally:
        await lazy.abort()
