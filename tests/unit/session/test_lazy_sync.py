import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from contree_client.models import FileResponse, InstanceResultState, OperationStatus, StreamRepr

from contree_sdk import ContreeSession, LazySession
from contree_sdk.files import UploadedFile, UploadFileSpec
from contree_sdk.session import AbstractSnapshotPolicy, CommandCountSnapshotPolicy, IdleSnapshotPolicy
from contree_sdk.session.snapshot_policy import DurationSnapshotPolicy
from tests.unit.session.factories import operation_response
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
        assert lazy.run("first").stdout == StreamRepr(value="first", encoding="ascii", truncated=False)
        assert lazy.run("second").stdout == StreamRepr(value="second", encoding="ascii", truncated=False)
        assert len(client.calls_for("spawn_instance")) == 1
        assert client.calls_for("spawn_instance")[0].kwargs["timeout"] == 3600
        assert client.calls_for("spawn_instance")[0].kwargs["args"] == ["infinity"]
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


def test_run_files_are_applied_before_subprocess_on_cold_and_running_vm(tmp_path):
    client = LiveClient()
    client.mock("apply_instance_file", None)
    client.mock("ensure_file", FileResponse(uuid="directory-file", sha256="a" * 64, size=4))
    source = tmp_path / "project"
    source.mkdir()
    (source / "script").write_bytes(b"data")
    (source / "script").chmod(0o755)
    base = ContreeSession(client, image="base")

    with LazySession(base) as lazy:
        lazy.run("first", files={"/first": UploadFileSpec(source=UploadedFile("first-file", "a" * 64))})
        lazy.run("second", files={"/app": source})
        assert len(client.calls_for("spawn_instance")) == 1
        assert client.calls_for("spawn_instance")[0].kwargs["files"] is Ellipsis
        calls = [call.operation for call in client.calls]
        applies = [index for index, name in enumerate(calls) if name == "apply_instance_file"]
        subprocesses = [index for index, name in enumerate(calls) if name == "operation_subprocess_create"]
        assert applies[0] < subprocesses[0]
        assert applies[1] < subprocesses[1]
        assert [call.args[2] for call in client.calls_for("apply_instance_file")] == ["/first", "/app/script"]
        lazy.snapshot(timeout=2)


def test_run_files_rejects_unsupported_live_metadata_before_start():
    client = LiveClient()
    lazy = LazySession(ContreeSession(client, image="base"))

    with pytest.raises(ValueError, match="cannot set uid, gid, or mode"):
        lazy.run("first", files={"/script": UploadFileSpec(source=b"data", mode=0o755)})

    assert not client.calls_for("spawn_instance")


def test_vm_deadline_drains_and_resumes_from_snapshot(monkeypatch):
    timers = ManualTimers()
    monkeypatch.setattr(
        "contree_sdk.session.lazy_sync.DurationSnapshotPolicy",
        lambda seconds: DurationSnapshotPolicy(seconds, timer_factory=timers.start),
    )
    client = LiveClient()
    with LazySession(
        ContreeSession(client, image="base"),
        snapshot_policy=IdleSnapshotPolicy(1000),
        vm_timeout=60,
        snapshot_timeout=10,
    ) as lazy:
        lazy.run("first")
        timers.advance(49)
        lazy.run("second")
        assert len(client.calls_for("spawn_instance")) == 1
        client.auto_exit = False
        handle = lazy.spawn("active")
        timers.advance(1)
        wait_state(lazy, lambda: lazy.phase == "draining")
        assert not client.calls_for("operation_subprocess_kill")
        with ThreadPoolExecutor(max_workers=1) as executor:
            following = executor.submit(lazy.run, "next")
            assert len(client.calls_for("operation_subprocess_create")) == 3
            client.auto_exit = True
            client.streams["op-1"].put(event("exit", handle.spid))
            assert following.result(timeout=2).stdout == StreamRepr(value="next", encoding="ascii", truncated=False)
        assert client.calls_for("spawn_instance")[1].args[1] == "image-op-1"
        assert all(call.kwargs["timeout"] == 60 for call in client.calls_for("spawn_instance"))
    assert all(timer.cancelled for timer in timers.timers)


@pytest.mark.parametrize("timeout", [0, -1, 30, float("inf"), float("nan")])
def test_invalid_vm_timeout(timeout):
    with pytest.raises(ValueError, match="vm_timeout"):
        LazySession(ContreeSession(LiveClient(), image="base"), vm_timeout=timeout)


def test_snapshot_with_unchanged_image_stops_vm_and_records_checkpoint(monkeypatch):
    client = LiveClient()
    monkeypatch.setattr(
        client,
        "get_operation_status",
        lambda operation_id, **kwargs: operation_response(operation_uuid=operation_id, result_image_uuid="base"),
    )
    base = ContreeSession(client, image="base")
    with LazySession(base) as lazy:
        lazy.run("true")
        first = lazy.snapshot(timeout=2)
        assert lazy.phase == "cold"

        lazy.run("true")
        second = lazy.snapshot(timeout=2)
        assert lazy.phase == "cold"

    assert first is not None
    assert second is not None
    assert first.image_uuid == second.image_uuid == "base"
    assert second.parent_id == first.id
    assert second.id != first.id
    assert len(base.history()[0]) == 3
    assert [call.args[1] for call in client.calls_for("spawn_instance")] == ["base", "base"]
    assert len(client.calls_for("operation_subprocess_kill")) == 2


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


def test_real_idle_timer_saves_without_another_session_call_across_vm_cycles():
    client = LiveClient()
    policy = IdleSnapshotPolicy(0.02)
    base = ContreeSession(client, image="base")
    lazy = LazySession(base, snapshot_policy=policy)
    try:
        for cycle in (1, 2):
            client.saving.clear()
            lazy.run(f"command-{cycle}")
            assert client.saving.wait(1)
            wait_state(lazy, lambda: lazy.state.phase == "cold")
            assert lazy.state.snapshots == cycle
            assert base.image_uuid == f"image-op-{cycle}"
            assert policy._timer is None
        assert [call.args[1] for call in client.calls_for("spawn_instance")] == ["base", "image-op-1"]
        assert len(client.calls_for("operation_subprocess_kill")) == 2
    finally:
        lazy.abort()
    assert lazy.worker is not None
    assert not lazy.worker.is_alive()
    assert policy.should_snapshot().cancelled()
    assert policy._timer is None
    assert lazy.duration_policy.timer is None


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
    state = lazy.run("false").state
    assert isinstance(state, InstanceResultState)
    assert state.exit_code == 3
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


def test_snapshot_preserves_another_actors_continuation():
    from contree_sdk.store import Node

    client = LiveClient()
    base = ContreeSession(client, image="base")
    lazy = LazySession(base)
    lazy.run("one")
    root = base.tip_id
    sibling = Node(parent_id=root, kind="run", data={"image_uuid": "external"})
    base.store.append(base.session_id, sibling)
    entry = lazy.snapshot(timeout=2)
    assert entry is not None
    assert entry.parent_id == root
    assert base.image_uuid == "image-op-1"
    assert (base.store.get_node(base.session_id, sibling.id)) == sibling
    assert len((base.store.list_children(base.session_id, root)).items) == 2
    lazy.close(timeout=2)


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


def test_staged_files_are_consumed_only_when_lazy_vm_is_snapshotted():
    from contree_sdk.files import UploadedFile, UploadFileSpec

    client = LiveClient()
    base = ContreeSession(client, image="base")
    staged = base.stage_files({"/input": UploadFileSpec(source=UploadedFile("upload", "a" * 64))})
    with LazySession(base) as lazy:
        lazy.run("cat /input")
        assert base.pending_files() == staged.attachments
        assert client.calls_for("spawn_instance")[0].kwargs["files"]["/input"].uuid == "upload"
        lazy.snapshot(timeout=2)
        assert base.pending_files() == ()
    base.rollback()
    assert base.pending_files() == staged.attachments


def test_rejected_snapshot_does_not_restart_from_stale_image():
    from contree_sdk.session import AbstractCommitPolicy

    class RejectSnapshot(AbstractCommitPolicy):
        def should_commit(self, context, result):
            return False

    client = LiveClient()
    base = ContreeSession(client, image="base", commit_policy=RejectSnapshot())
    lazy = LazySession(base)
    lazy.run("write")
    try:
        with pytest.raises(RuntimeError):
            lazy.snapshot(timeout=2)
        assert lazy.last_entry is None
        assert base.image_uuid == "base"
        assert len((base.history())[0]) == 1
        with pytest.raises(RuntimeError):
            lazy.run("read")
        assert len(client.calls_for("spawn_instance")) == 1
    finally:
        lazy.abort()


@pytest.mark.parametrize("override", ["keepalive", "prepare_request"])
@pytest.mark.parametrize(("vm_timeout", "effective_timeout", "startup"), [(3600, 60, 20), (60, 120, 55)])
def test_vm_deadline_uses_effective_timeout_and_original_start_time(override, vm_timeout, effective_timeout, startup):
    timers = ManualTimers()

    class SlowClient(LiveClient):
        def spawn_instance(self, command, image, **kwargs):
            response = super().spawn_instance(command, image, **kwargs)
            timers.advance(startup)
            return response

    class CustomSession(ContreeSession):
        def prepare_request(self, request):
            request = super().prepare_request(request)
            if override == "prepare_request" and request.command == "sleep":
                return replace(request, timeout=effective_timeout)
            return request

    class CustomLazy(LazySession):
        def keepalive_request(self):
            request = super().keepalive_request()
            return replace(request, timeout=effective_timeout) if override == "keepalive" else request

    client = SlowClient()
    lazy = CustomLazy(CustomSession(client, image="base"), snapshot_timeout=10, vm_timeout=vm_timeout)
    lazy.duration_policy.timer_factory = timers.start
    lazy.duration_policy.clock = lambda: timers.now
    with lazy:
        lazy.run("first")
        assert client.calls_for("spawn_instance")[0].kwargs["timeout"] == effective_timeout
        deadline = effective_timeout - 10
        assert lazy.duration_policy.seconds == deadline
        assert timers.timers[-1].deadline == deadline
        timers.advance(deadline - startup - 1)
        lazy.run("second")
        assert len(client.calls_for("spawn_instance")) == 1
        timers.advance(1)
        wait_state(lazy, lambda: lazy.phase == "cold")
        effective_timeout *= 2
        startup = deadline + 5
        lazy.run("third")
        assert client.calls_for("spawn_instance")[1].args[1] == "image-op-1"
        assert timers.timers[-1].deadline == deadline + effective_timeout - 10
        assert not lazy.duration_policy.should_snapshot().done()
    assert all(timer.cancelled for timer in timers.timers)


@pytest.mark.parametrize("inspection", [False, True])
def test_vm_deadline_expiring_during_startup_rejects_admission(inspection):
    timers = ManualTimers()

    class SlowClient(LiveClient):
        def spawn_instance(self, command, image, **kwargs):
            response = super().spawn_instance(command, image, **kwargs)
            timers.advance(60)
            return response

    client = SlowClient()
    base = ContreeSession(client, image="base")
    if inspection:
        base.stage_files({"/input": UploadFileSpec(source=UploadedFile("upload", "a" * 64))})
    lazy = LazySession(base, vm_timeout=60, snapshot_timeout=10)
    lazy.duration_policy.timer_factory = timers.start
    lazy.duration_policy.clock = lambda: timers.now
    try:
        if inspection:
            with (
                pytest.raises(TimeoutError, match="renewal deadline expired during startup"),
                lazy.inspection_source(),
            ):
                pytest.fail("inspection was admitted after the deadline")
        else:
            with pytest.raises(TimeoutError, match="renewal deadline expired during startup"):
                lazy.run("first")
        assert not client.calls_for("operation_subprocess_create")
        assert client.calls_for("cancel_operation")
        assert lazy.worker is None
        assert all(timer.cancelled for timer in timers.timers)
    finally:
        lazy.abort()


def test_inspection_spawn_failure_cancels_duration_timer_without_worker():
    timers = ManualTimers()

    class FailedSpawnClient(LiveClient):
        def spawn_instance(self, command, image, **kwargs):
            raise OSError("spawn failed")

    base = ContreeSession(FailedSpawnClient(), image="base")
    base.stage_files({"/input": UploadFileSpec(source=UploadedFile("upload", "a" * 64))})
    lazy = LazySession(base)
    lazy.duration_policy.timer_factory = timers.start
    try:
        with pytest.raises(OSError, match="spawn failed"), lazy.inspection_source():
            pytest.fail("inspection was admitted after spawn failure")
        assert lazy.worker is None
        assert lazy.duration_policy.should_snapshot().cancelled()
        assert all(timer.cancelled for timer in timers.timers)
    finally:
        lazy.abort()


@pytest.mark.parametrize("timeout", [None, 0, -1, 30])
def test_invalid_effective_keepalive_timeout_is_rejected(timeout):
    class CustomLazy(LazySession):
        def keepalive_request(self):
            return replace(super().keepalive_request(), timeout=timeout)

    client = LiveClient()
    lazy = CustomLazy(ContreeSession(client, image="base"))
    try:
        with pytest.raises(ValueError, match="keepalive timeout"):
            lazy.run("first")
        assert not client.calls_for("operation_subprocess_create")
        assert lazy.duration_policy.timer is None
    finally:
        lazy.abort()
