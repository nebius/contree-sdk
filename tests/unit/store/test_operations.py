"""Registry completion and its history update share one atomic store operation."""

import asyncio
import inspect
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from contree_sdk.exceptions import SessionConflictError
from contree_sdk.store import AsyncMemoryStore, AsyncSQLiteStore, OperationRecord, SyncMemoryStore, SyncSQLiteStore


async def call(target, method, *args, **kwargs):
    result = getattr(target, method)(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


def record(root, uuid="op"):
    return OperationRecord(
        uuid=uuid,
        session_id="s",
        parent_id=root.id,
        image_uuid="base",
        branch="main",
        title="write",
        disposable=False,
        request_json='{"command": "write"}',
        files=("/input",),
    )


@pytest.fixture(params=["memory", "sqlite", "async-memory", "async-sqlite"])
async def store(request, tmp_path):
    factories = {
        "memory": SyncMemoryStore,
        "sqlite": lambda: SyncSQLiteStore(tmp_path / "store.db"),
        "async-memory": AsyncMemoryStore,
        "async-sqlite": lambda: AsyncSQLiteStore(tmp_path / "store.db"),
    }
    instance = factories[request.param]()
    yield instance
    await call(instance, "close")


async def test_registration_is_immutable_and_scoped_to_session(store):
    root = await call(store, "append", "s", image_uuid="base", parent_id=None)
    pending = record(root)
    assert await call(store, "register_operation", pending) == pending
    assert await call(store, "register_operation", pending) == pending
    with pytest.raises(ValueError, match="another context"):
        await call(store, "register_operation", replace(pending, title="changed"))
    with pytest.raises(ValueError):
        await call(store, "register_operation", replace(pending, image_uuid="wrong"))
    with pytest.raises(ValueError):
        await call(store, "register_operation", replace(pending, session_id="other"))
    with pytest.raises(ValueError):
        await call(store, "get_operation", "other", "op")
    assert await call(store, "list_operations", "s") == (pending,)


async def test_first_completion_wins_without_moving_active_branch(store):
    root = await call(store, "append", "s", image_uuid="base", parent_id=None)
    pending = record(root)
    await call(store, "register_operation", pending)
    await call(store, "create_branch", "s", "other")
    await call(store, "switch_branch", "s", "other")
    first = await call(store, "finish_operation", "s", "op", '{"result": 1}', image_uuid="result")
    second = await call(store, "finish_operation", "s", "op", '{"result": 2}', image_uuid="wrong", branch="unused")
    assert first == second
    assert await call(store, "register_operation", pending) == first
    assert await call(store, "list_operations", "s") == ()
    assert await call(store, "active_branch", "s") == "other"
    assert await call(store, "tip", "s") == root
    committed = await call(store, "get_entry", "s", first.history_id)
    assert committed.parent_id == root.id
    assert committed.image_uuid == "result"
    assert committed.applied_files == ("/input",)
    assert len((await call(store, "history_dag", "s"))[0]) == 2


async def test_discarded_completion_cannot_later_commit(store):
    root = await call(store, "append", "s", image_uuid="base", parent_id=None)
    await call(store, "register_operation", record(root))
    first = await call(store, "finish_operation", "s", "op", "{}")
    assert first.history_id is None
    assert await call(store, "finish_operation", "s", "op", "{}", image_uuid="ignored") == first
    assert len((await call(store, "history_dag", "s"))[0]) == 1


async def test_conflict_rolls_back_completion_and_delete_removes_registry(store):
    root = await call(store, "append", "s", image_uuid="base", parent_id=None)
    await call(store, "register_operation", record(root))
    newer = await call(store, "append", "s", image_uuid="newer", parent_id=root.id)
    with pytest.raises(SessionConflictError):
        await call(store, "finish_operation", "s", "op", "{}", image_uuid="result")
    assert (await call(store, "get_operation", "s", "op")).pending
    assert await call(store, "tip", "s") == newer
    assert await call(store, "delete_session", "s")
    assert await call(store, "list_operations", "s", pending_only=False) == ()
    with pytest.raises(ValueError):
        await call(store, "finish_operation", "s", "op", "{}")


def test_two_sync_connections_complete_once(tmp_path):
    path = tmp_path / "race.db"
    with SyncSQLiteStore(path) as first, SyncSQLiteStore(path) as second:
        root = first.append("s", image_uuid="base", parent_id=None)
        first.register_operation(record(root))
        barrier = threading.Barrier(2)

        def finish(store):
            barrier.wait(timeout=2)
            return store.finish_operation("s", "op", "{}", image_uuid="result")

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(finish, store) for store in (first, second)]
            outcomes = [future.result(timeout=5) for future in futures]
        assert outcomes[0] == outcomes[1]
        assert len(first.history_dag("s")[0]) == 2


async def test_two_async_connections_complete_once(tmp_path):
    path = tmp_path / "race.db"
    async with AsyncSQLiteStore(path) as first, AsyncSQLiteStore(path) as second:
        root = await first.append("s", image_uuid="base", parent_id=None)
        await first.register_operation(record(root))
        outcomes = await asyncio.gather(
            first.finish_operation("s", "op", "{}", image_uuid="result"),
            second.finish_operation("s", "op", "{}", image_uuid="result"),
        )
        assert outcomes[0] == outcomes[1]
        assert len((await first.history_dag("s"))[0]) == 2


@pytest.mark.parametrize("async_mode", [False, True])
async def test_failed_completion_write_rolls_back_history(tmp_path, async_mode):
    store = AsyncSQLiteStore(tmp_path / "failure.db") if async_mode else SyncSQLiteStore(tmp_path / "failure.db")
    try:
        root = await call(store, "append", "s", image_uuid="base", parent_id=None)
        await call(store, "register_operation", record(root))
        conn = await store.ensure_connection() if isinstance(store, AsyncSQLiteStore) else store.conn
        await call(
            conn,
            "execute",
            "CREATE TRIGGER reject_completion BEFORE UPDATE ON session_operations_v1 "
            "BEGIN SELECT RAISE(FAIL, 'write failed'); END",
        )
        with pytest.raises(sqlite3.IntegrityError, match="write failed"):
            await call(store, "finish_operation", "s", "op", "{}", image_uuid="result")
        assert (await call(store, "get_operation", "s", "op")).pending
        assert await call(store, "tip", "s") == root
        assert len((await call(store, "history_dag", "s"))[0]) == 1
        await call(conn, "execute", "DROP TRIGGER reject_completion")
        final = await call(store, "finish_operation", "s", "op", "{}", image_uuid="result")
        assert final.history_id is not None
    finally:
        await call(store, "close")


async def test_async_cancellation_rolls_back_history_and_registry(tmp_path, monkeypatch):
    async with AsyncSQLiteStore(tmp_path / "cancel.db") as store:
        root = await store.append("s", image_uuid="base", parent_id=None)
        await store.register_operation(record(root))
        appended = asyncio.Event()
        original = store._append

        async def delay(*args, **kwargs):
            await original(*args, **kwargs)
            appended.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(store, "_append", delay)
        task = asyncio.create_task(store.finish_operation("s", "op", "{}", image_uuid="result"))
        await asyncio.wait_for(appended.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert (await store.get_operation("s", "op")).pending
        assert await store.tip("s") == root
        monkeypatch.setattr(store, "_append", original)
        await store.finish_operation("s", "op", "{}", image_uuid="result")
        assert len((await store.history_dag("s"))[0]) == 2
