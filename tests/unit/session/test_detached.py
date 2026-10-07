"""Detached workflows exercise real sessions and stores across reopen boundaries."""

import inspect
import io
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from contree_client.models import FileResponse, InstanceNetworking, InstanceResourcesLimits, OperationStatus
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk import ContreeAsyncSession, ContreeSession
from contree_sdk.exceptions import FailedOperationError, SessionConflictError
from contree_sdk.files import UploadFileSpec
from contree_sdk.session import ZeroExitCommitPolicy
from contree_sdk.store import AsyncMemoryStore, AsyncSQLiteStore, SyncMemoryStore, SyncSQLiteStore
from tests.unit.session.factories import mock_completion, operation_response, spawn_response


async def call(target, method, *args, **kwargs):
    result = getattr(target, method)(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


@pytest.fixture(params=["memory", "sqlite", "async-memory", "async-sqlite"])
async def session(request, tmp_path):
    factories = {
        "memory": SyncMemoryStore,
        "sqlite": lambda: SyncSQLiteStore(tmp_path / "session.db"),
        "async-memory": AsyncMemoryStore,
        "async-sqlite": lambda: AsyncSQLiteStore(tmp_path / "session.db"),
    }
    store = factories[request.param]()
    instance: ContreeSession | ContreeAsyncSession
    if isinstance(store, (AsyncMemoryStore, AsyncSQLiteStore)):
        client = ContreeAsyncClient()
        client.mock("resolve_image", "base")
        instance = ContreeAsyncSession(client, image="base", session_id="session", store=store)
        await instance.ensure_ready()
    else:
        client = ContreeClient()
        client.mock("resolve_image", "base")
        instance = ContreeSession(client, image="base", session_id="session", store=store)
    client.mock("spawn_instance", spawn_response())
    yield instance
    await call(instance.store, "close")


async def reopen(session, tmp_path):
    if isinstance(session.store, (SyncSQLiteStore, AsyncSQLiteStore)):
        await call(session.store, "close")
        session.store = type(session.store)(tmp_path / "session.db")
    return type(session)(session.client, store=session.store, session_id=session.session_id)


async def test_reopen_finish_and_replay_without_transport(session, tmp_path):
    record = await call(session, "spawn_detached", "false", disposable=False)
    assert record.pending
    assert not session.client.calls_for("follow_operation_events")
    resumed = await reopen(session, tmp_path)
    mock_completion(session.client, operation_response(exit_code=7))
    first = await call(resumed, "wait_operation", record.uuid)
    final = await call(resumed.store, "get_operation", resumed.session_id, record.uuid)
    assert not final.pending
    assert final.history_id is not None
    assert await call(resumed, "list_operations") == ()
    assert await call(resumed, "list_operations", pending_only=False) == (final,)
    second = await call(resumed, "wait_operation", record.uuid)
    assert first == second
    assert len(session.client.calls_for("follow_operation_events")) == 1
    assert len((await call(resumed, "history"))[0]) == 2
    assert resumed.image_uuid == "img-uuid-1"


async def test_restored_operation_commits_once_on_original_branch(session):
    record = await call(session, "spawn_detached", "write", disposable=False)
    await call(session, "create_branch", "other")
    await call(session, "switch_branch", "other")
    mock_completion(session.client, operation_response())
    operation = await call(session, "restore_operation", record.uuid)
    await call(operation, "wait")
    first = await call(session, "commit_result", operation)
    second = await call(session, "commit_result", operation)
    assert first == second
    assert first is not None
    assert await call(session.store, "active_branch", session.session_id) == "other"
    assert session.image_uuid == "base"
    assert (await call(session.store, "tip", session.session_id, "main")).id == first.id
    assert len((await call(session, "history"))[0]) == 2


async def test_conflict_can_finish_on_new_branch_without_switching(session):
    record = await call(session, "spawn_detached", "write", disposable=False)
    root = session.tip_id
    newer = await call(session.store, "append", session.session_id, image_uuid="newer", parent_id=root)
    mock_completion(session.client, operation_response())
    with pytest.raises(SessionConflictError):
        await call(session, "wait_operation", record.uuid)
    assert (await call(session.store, "get_operation", session.session_id, record.uuid)).pending
    await call(session, "wait_operation", record.uuid, branch="saved")
    assert session.tip_id == newer.id
    assert await call(session.store, "active_branch", session.session_id) == "main"
    saved = await call(session.store, "tip", session.session_id, "saved")
    assert saved.parent_id == root
    assert saved.image_uuid == "img-uuid-1"


@pytest.mark.parametrize("disposable", [False, True])
async def test_disposable_and_rejected_results_remain_replayable(session, disposable):
    session.commit_policy = ZeroExitCommitPolicy()
    record = await call(session, "spawn_detached", "false", disposable=disposable)
    mock_completion(session.client, operation_response(exit_code=3))
    await call(session, "wait_operation", record.uuid)
    final = await call(session.store, "get_operation", session.session_id, record.uuid)
    assert not final.pending
    assert final.history_id is None
    assert len((await call(session, "history"))[0]) == 1
    # A different policy after completion cannot turn the stored outcome into a commit.
    resumed = type(session)(session.client, store=session.store, session_id=session.session_id)
    await call(resumed, "wait_operation", record.uuid)
    assert len((await call(session, "history"))[0]) == 1


@pytest.mark.parametrize(
    ("status", "error"), [(OperationStatus.FAILED, FailedOperationError), (OperationStatus.CANCELLED, InterruptedError)]
)
async def test_final_errors_are_stored_and_replayed(session, status, error):
    record = await call(session, "spawn_detached", "write", disposable=False)
    mock_completion(session.client, operation_response(status=status))
    session.client.mock("cancel_operation", None)
    for _ in range(2):
        with pytest.raises(error):
            await call(session, "wait_operation", record.uuid)
    assert not (await call(session.store, "get_operation", session.session_id, record.uuid)).pending
    assert len((await call(session, "history"))[0]) == 1
    assert len(session.client.calls_for("follow_operation_events")) == 1


async def test_transport_error_does_not_complete_registry(session):
    record = await call(session, "spawn_detached", "write", disposable=False)
    mock_completion(session.client, error=OSError("status unavailable"))
    session.client.mock("cancel_operation", None)
    with pytest.raises(OSError, match="status unavailable"):
        await call(session, "wait_operation", record.uuid)
    assert (await call(session.store, "get_operation", session.session_id, record.uuid)).pending


async def test_streams_are_not_serialized_but_effective_metadata_is(session, tmp_path):
    session.client.mock("ensure_file", FileResponse(uuid="upload", sha256="a" * 64, size=3))
    content = tmp_path / "input.bin"
    content.write_bytes(b"abc")
    stdin = io.BytesIO(b"input")
    record = await call(
        session,
        "spawn_detached",
        "cat",
        args=["/data"],
        disposable=False,
        env={"KEY": "value"},
        cwd="/work",
        uid=123,
        gid=456,
        timeout=timedelta(seconds=10),
        stdin=stdin,
        files={"/data": UploadFileSpec(source=content, uid=12, gid=34, mode=0o640)},
        resources_limits=InstanceResourcesLimits(),
        networking=InstanceNetworking(enabled=False),
    )
    assert not stdin.closed
    content.unlink()
    stdin.close()
    resumed = await reopen(session, tmp_path)
    operation = await call(resumed, "restore_operation", record.uuid)
    context = operation.context
    assert context.detached
    assert context.request.stdin is None
    assert context.request.files is None
    assert context.request.timeout == 10
    assert context.request.env == {"KEY": "value"}
    assert (context.request.cwd, context.request.uid, context.request.gid) == ("/work", 123, 456)
    assert context.request.networking.enabled is False
    assert context.attachments[0].uuid == "upload"
    assert (context.attachments[0].uid, context.attachments[0].gid, context.attachments[0].mode) == (12, 34, 0o640)
    assert len(session.client.calls_for("ensure_file")) == 1


async def test_registration_failure_cancels_remote_operation(session, monkeypatch):
    def fail(record):
        raise OSError("registry unavailable")

    async def async_fail(record):
        fail(record)

    monkeypatch.setattr(
        session.store, "register_operation", async_fail if isinstance(session, ContreeAsyncSession) else fail
    )
    session.client.mock("cancel_operation", None)
    with pytest.raises(OSError, match="registry unavailable"):
        await call(session, "spawn_detached", "write", disposable=False)
    assert session.client.calls_for("cancel_operation")[0].args == ("op-1",)


def test_independent_process_restores_and_commits(tmp_path):
    db = tmp_path / "process.db"
    client = ContreeClient()
    client.mock("resolve_image", "base")
    client.mock("spawn_instance", spawn_response())
    with SyncSQLiteStore(db) as store:
        session = ContreeSession(client, image="base", session_id="session", store=store)
        session.spawn_detached("write", disposable=False)
    script = """
import sys
from contree_client.testing import ContreeClient
from contree_sdk import ContreeSession
from contree_sdk.store import SyncSQLiteStore
from tests.unit.session.factories import mock_completion, operation_response
client = ContreeClient()
mock_completion(client, operation_response())
with SyncSQLiteStore(sys.argv[1]) as store:
    session = ContreeSession(client, session_id="session", store=store)
    session.wait_operation("op-1")
    session.wait_operation("op-1")
    assert len(session.history()[0]) == 2
"""
    subprocess.run(  # noqa: S603 - fixed local interpreter and test script
        [sys.executable, "-c", script, str(db)], cwd=Path(__file__).resolve().parents[3], check=True, timeout=10
    )
    with SyncSQLiteStore(db) as store:
        assert not store.get_operation("session", "op-1").pending
        assert len(store.history_dag("session")[0]) == 2


@pytest.mark.parametrize("completed", [False, True])
async def test_another_endpoint_cannot_restore_or_finish_record(session, completed):
    record = await call(session, "spawn_detached", "write", disposable=False)
    mock_completion(session.client, operation_response())
    if completed:
        await call(session, "wait_operation", record.uuid)
    calls_before = len(session.client.calls)
    session.client.base_url = "https://another.invalid"
    for method in ("restore_operation", "wait_operation"):
        with pytest.raises(ValueError, match="different endpoint"):
            await call(session, method, record.uuid)
    assert len(session.client.calls) == calls_before


async def test_multiple_operations_are_listed_and_completed_independently(session):
    session.client.mock("spawn_instance", spawn_response("op-2"))
    first = await call(session, "spawn_detached", "one")
    second = await call(session, "spawn_detached", "two")
    assert [item.uuid for item in await call(session, "list_operations")] == [first.uuid, second.uuid]
    mock_completion(session.client, operation_response(operation_uuid=second.uuid))
    await call(session, "wait_operation", second.uuid)
    assert await call(session, "list_operations") == (first,)
    assert len((await call(session, "history"))[0]) == 1


async def test_retained_result_consumes_staging_once(session):
    session.client.mock("ensure_file", FileResponse(uuid="upload", sha256="a" * 64, size=4))
    staged = await call(session, "stage_files", {"/input": b"data"})
    record = await call(session, "spawn_detached", "write", disposable=False)
    assert record.parent_id == staged.id
    assert record.attachments[0].uuid == "upload"
    mock_completion(session.client, operation_response())
    await call(session, "wait_operation", record.uuid)
    assert await call(session, "pending_files") == ()
    await call(session, "rollback")
    # A replay does not move the branch back to the committed entry.
    await call(session, "wait_operation", record.uuid)
    assert session.tip_id == staged.id
    assert len(await call(session, "pending_files")) == 1


async def test_success_without_result_image_remains_pending(session):
    record = await call(session, "spawn_detached", "write", disposable=False)
    mock_completion(session.client, operation_response(result_image_uuid=None))
    with pytest.raises(ValueError, match="no result image"):
        await call(session, "wait_operation", record.uuid)
    assert (await call(session.store, "get_operation", session.session_id, record.uuid)).pending
    assert len((await call(session, "history"))[0]) == 1


async def test_custom_serialization_hooks_are_used_for_restore_and_commit(session, monkeypatch):
    import json
    from dataclasses import replace

    encode = session.create_operation_record
    decode = session.restore_operation_context
    decoded = []

    def create_record(operation):
        saved = encode(operation)
        payload = json.loads(saved.request_json)
        payload["application"] = {"label": "custom"}
        return replace(saved, request_json=json.dumps(payload))

    def restore_context(saved):
        payload = json.loads(saved.request_json)
        decoded.append(payload.pop("application"))
        return decode(replace(saved, request_json=json.dumps(payload)))

    monkeypatch.setattr(session, "create_operation_record", create_record)
    monkeypatch.setattr(session, "restore_operation_context", restore_context)
    record = await call(session, "spawn_detached", "write", disposable=False)
    mock_completion(session.client, operation_response())
    await call(session, "wait_operation", record.uuid)
    assert decoded == [{"label": "custom"}, {"label": "custom"}]
    assert len((await call(session, "history"))[0]) == 2


async def test_sync_registration_can_complete_with_async_session(tmp_path):
    path = tmp_path / "mixed.db"
    client = ContreeClient()
    client.mock("resolve_image", "base")
    client.mock("spawn_instance", spawn_response())
    with SyncSQLiteStore(path) as store:
        session = ContreeSession(client, image="base", session_id="s", store=store)
        record = session.spawn_detached("write", disposable=False)
    async_client = ContreeAsyncClient()
    mock_completion(async_client, operation_response())
    async with AsyncSQLiteStore(path) as store:
        resumed = ContreeAsyncSession(async_client, session_id="s", store=store)
        await resumed.wait_operation(record.uuid)
    with SyncSQLiteStore(path) as store:
        replay = ContreeSession(client, session_id="s", store=store)
        replay.wait_operation(record.uuid)
        assert len(replay.history()[0]) == 2
    assert not client.calls_for("follow_operation_events")


async def test_registry_error_preserves_primary_operation_failure(session, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("registry write failed")

    async def async_fail(*args, **kwargs):
        fail()

    record = await call(session, "spawn_detached", "write", disposable=False)
    mock_completion(session.client, operation_response(status=OperationStatus.FAILED))
    session.client.mock("cancel_operation", None)
    monkeypatch.setattr(
        session.store, "finish_operation", async_fail if isinstance(session, ContreeAsyncSession) else fail
    )
    with pytest.raises(FailedOperationError) as raised:
        await call(session, "wait_operation", record.uuid)
    assert isinstance(raised.value.__cause__, OSError)
    assert str(raised.value.__cause__) == "registry write failed"
    assert (await call(session.store, "get_operation", session.session_id, record.uuid)).pending
