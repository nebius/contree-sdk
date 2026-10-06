import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from contree_client.models import InstanceResultState, OperationStatus, StreamRepr

from contree_sdk import ContreeSession, LazySession
from contree_sdk.session import AbstractSnapshotPolicy, CommandCountSnapshotPolicy, IdleSnapshotPolicy
from tests.unit.session.lazy_clients import LiveClient, event
from tests.unit.session.timers import ManualTimers


def wait_state(lazy, predicate):
    with lazy.condition:
        assert lazy.condition.wait_for(predicate, timeout=2)


def test_shared_vm_snapshot_and_next_image():
    client = LiveClient()
    base = ContreeSession(client, image="base")
    with LazySession(base) as lazy:
        assert not client.calls_for("spawn_instance")
        assert lazy.run("first").stdout == StreamRepr.from_text("first")
        assert lazy.run("second").stdout == StreamRepr.from_text("second")
        assert len(client.calls_for("spawn_instance")) == 1
        assert len(client.calls_for("follow_operation_events")) == 1
        assert len(base.history()[0]) == 1
        entry = lazy.snapshot(timeout=2)
        assert entry is not None
        assert entry.image_uuid == "image-op-1"
        assert len(base.history()[0]) == 2
        lazy.run("third")
        assert client.calls_for("spawn_instance")[1].args[1] == "image-op-1"
    assert lazy.phase == "closed"
    assert lazy.worker is not None
    assert not lazy.worker.is_alive()
    assert len(base.history()[0]) == 3


def test_idle_timer_uses_exit_without_wait_and_does_not_stop_active_vm():
    client = LiveClient()
    client.auto_exit = False
    timers = ManualTimers()
    lazy = LazySession(
        ContreeSession(client, image="base"), snapshot_policy=IdleSnapshotPolicy(5, timer_factory=timers.start)
    )
    try:
        handle = lazy.spawn("long")
        timers.advance(100)
        assert not client.calls_for("operation_subprocess_kill")
        client.streams["op-1"].put(event("exit", handle.spid))
        wait_state(lazy, lambda: not lazy.state.active)
        timers.advance(5)
        wait_state(lazy, lambda: lazy.phase == "cold")
        assert len(client.calls_for("get_operation_status")) == 1
    finally:
        lazy.abort()


def test_count_reserves_exactly_n_and_waits_for_snapshot_before_next_command():
    client = LiveClient()
    client.wait_gate = threading.Event()
    lazy = LazySession(ContreeSession(client, image="base"), snapshot_policy=CommandCountSnapshotPolicy(2))
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            one = pool.submit(lazy.run, "one")
            two = pool.submit(lazy.run, "two")
            one.result(2)
            two.result(2)
            assert client.saving.wait(2)
            three = pool.submit(lazy.run, "three")
            assert len(client.calls_for("operation_subprocess_create")) == 2
            client.wait_gate.set()
            three.result(2)
        assert [call.args[0] for call in client.calls_for("operation_subprocess_create")] == ["op-1", "op-1", "op-2"]
    finally:
        client.wait_gate.set()
        lazy.close(timeout=2)


@pytest.mark.parametrize("failure", [OSError("stream broken"), None, event("exit", 1)])
def test_unexpected_stream_end_does_not_claim_snapshot(failure):
    client = LiveClient()
    client.auto_exit = False
    base = ContreeSession(client, image="base")
    lazy = LazySession(base)
    lazy.spawn("long")
    client.streams["op-1"].put(failure)
    wait_state(lazy, lambda: lazy.error is not None)
    with pytest.raises(RuntimeError):
        lazy.snapshot(timeout=2)
    assert len(base.history()[0]) == 1
    lazy.abort()
    assert lazy.worker is not None
    assert not lazy.worker.is_alive()


@pytest.mark.parametrize("missing_image", [False, True])
def test_snapshot_failure_preserves_history(missing_image):
    client = LiveClient()
    client.result_image = not missing_image
    if not missing_image:
        client.wait_error = OSError("wait failed")
    base = ContreeSession(client, image="base")
    lazy = LazySession(base)
    lazy.run("one")
    with pytest.raises(RuntimeError):
        lazy.snapshot(timeout=2)
    assert base.image_uuid == "base"
    assert len(base.history()[0]) == 1
    lazy.abort()


def test_create_failure_nonzero_result_and_history_boundary():
    client = LiveClient()
    client.exit_code = 3
    base = ContreeSession(client, image="base")
    lazy = LazySession(base)
    assert lazy.run("false").state == InstanceResultState(exit_code=3)
    with pytest.raises(RuntimeError, match="snapshot"):
        lazy.rollback()
    with pytest.raises(ValueError, match="disposable"):
        lazy.run("echo", disposable=True)
    lazy.snapshot(timeout=2)
    lazy.create_branch("experiment")
    lazy.switch_branch("experiment")
    client.create_error = OSError("create failed")
    with pytest.raises(OSError):
        lazy.spawn("broken")
    with pytest.raises(RuntimeError):
        lazy.close(timeout=2)
    assert lazy.phase == "closed"


def test_timeout_kills_only_the_subprocess():
    client = LiveClient()
    client.auto_exit = False
    lazy = LazySession(ContreeSession(client, image="base"))
    try:
        with pytest.raises(TimeoutError):
            lazy.run("long", timeout=0.01)
        call = client.calls_for("operation_subprocess_kill")[0]
        assert call.args == ("op-1", 2)
        assert call.kwargs["signal"] == "SIGKILL"
    finally:
        lazy.close(timeout=2)


def test_snapshot_conflict_keeps_response_for_recovery():
    client = LiveClient()
    base = ContreeSession(client, image="base")
    lazy = LazySession(base)
    lazy.run("one")
    base.store.append(base.session_id, image_uuid="external", parent_id=base.tip_id)
    with pytest.raises(RuntimeError):
        lazy.snapshot(timeout=2)
    from contree_sdk.exceptions import SessionConflictError

    assert isinstance(lazy.error, SessionConflictError)
    assert lazy.operation is not None
    assert lazy.operation.response is not None
    assert lazy.operation.response.result_image_uuid == "image-op-1"
    tip = base.store.tip(base.session_id)
    assert tip is not None
    assert tip.image_uuid == "external"
    lazy.abort()


def test_pending_create_excludes_timer_and_close_until_admission_finishes():
    client = LiveClient()
    client.create_gate = threading.Event()
    lazy = LazySession(ContreeSession(client, image="base"), snapshot_policy=CommandCountSnapshotPolicy(1))
    with ThreadPoolExecutor(max_workers=2) as pool:
        command = pool.submit(lazy.run, "one")
        assert client.created.wait(2)
        closing = pool.submit(lazy.close, timeout=2)
        assert not client.calls_for("operation_subprocess_kill")
        client.create_gate.set()
        command.result(2)
        closing.result(2)
    assert len(client.calls_for("spawn_instance")) == 1
    assert len(client.calls_for("follow_operation_events")) == 1
    assert not client.calls_for("wait_operation")


def test_eof_reaches_handle_wait_instead_of_returning_a_synthetic_result():
    client = LiveClient()
    client.auto_exit = False
    lazy = LazySession(ContreeSession(client, image="base"))
    handle = lazy.spawn("long")
    client.streams["op-1"].put(None)
    with pytest.raises(RuntimeError, match="completion"):
        handle.wait(timeout=2)
    lazy.abort()


def test_snapshot_wait_timeout_does_not_cancel_active_work():
    client = LiveClient()
    client.auto_exit = False
    lazy = LazySession(ContreeSession(client, image="base"))
    handle = lazy.spawn("long")
    with pytest.raises(TimeoutError):
        lazy.snapshot(timeout=0.001)
    assert not client.calls_for("operation_subprocess_kill")
    client.streams["op-1"].put(event("exit", handle.spid))
    lazy.close(timeout=2)


def test_cold_close_and_context_exception_release_resources():
    client = LiveClient()
    lazy = LazySession(ContreeSession(client, image="base"))
    with lazy:
        assert lazy.snapshot() is None
    lazy.close()
    lazy.close()
    assert not client.calls_for("spawn_instance")
    with pytest.raises(ValueError, match="application"), LazySession(ContreeSession(client, image="base")) as lazy:  # noqa: PT012 - exercise exceptional context exit
        lazy.run("one")
        raise ValueError("application")
    assert client.calls_for("cancel_operation")
    assert not client.calls_for("get_operation_status")


def test_idle_deadline_during_startup_still_admits_first_command():
    timers = ManualTimers()

    class SlowStartClient(LiveClient):
        def spawn_instance(self, command, image, **kwargs):
            response = super().spawn_instance(command, image, **kwargs)
            timers.advance(100)
            return response

    client = SlowStartClient()
    with LazySession(
        ContreeSession(client, image="base"), snapshot_policy=IdleSnapshotPolicy(5, timer_factory=timers.start)
    ) as lazy:
        lazy.run("first")
        assert len(client.calls_for("spawn_instance")) == 1
        assert len(client.calls_for("operation_subprocess_create")) == 1


@pytest.mark.parametrize("status", [OperationStatus.FAILED, OperationStatus.CANCELLED])
def test_unsuccessful_snapshot_never_advances_history(status):
    client = LiveClient()
    client.final_status = status
    base = ContreeSession(client, image="base")
    lazy = LazySession(base)
    lazy.run("one")
    with pytest.raises(RuntimeError, match="snapshot"):
        lazy.snapshot(timeout=2)
    assert base.image_uuid == "base"
    assert len(base.history()[0]) == 1
    lazy.abort()


def test_custom_future_wakes_controller_but_does_not_stop_active_command():
    class ManualPolicy(AbstractSnapshotPolicy):
        def notify(self, event):
            super().notify(event)

    client = LiveClient()
    client.auto_exit = False
    policy = ManualPolicy()
    lazy = LazySession(ContreeSession(client, image="base"), snapshot_policy=policy)
    handle = lazy.spawn("long")
    policy.future.set_result(None)
    wait_state(lazy, lambda: lazy.phase == "draining")
    assert not client.calls_for("operation_subprocess_kill")
    client.streams["op-1"].put(event("exit", handle.spid))
    wait_state(lazy, lambda: lazy.phase == "cold")
    lazy.close(timeout=2)


def test_policy_future_failure_wakes_controller_and_preserves_error():
    class FailingPolicy(AbstractSnapshotPolicy):
        def notify(self, event):
            super().notify(event)

    client = LiveClient()
    policy = FailingPolicy()
    lazy = LazySession(ContreeSession(client, image="base"), snapshot_policy=policy)
    lazy.run("one")
    error = ValueError("policy decision failed")
    policy.future.set_exception(error)
    wait_state(lazy, lambda: lazy.phase == "failed")
    assert lazy.error is error
    lazy.abort()
