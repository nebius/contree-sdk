"""Public SQLite queries read one database snapshot across all their SELECTs."""

import asyncio
import sqlite3
import threading

import pytest

from contree_sdk.store import StagedFile
from tests.unit.store.test_mutation_transactions import connection, invoke


@pytest.fixture(params=["sync", "async"])
async def read_connections(request, tmp_path):
    from contree_sdk.store import AsyncSQLiteStore, SyncSQLiteStore

    factory = AsyncSQLiteStore if request.param == "async" else SyncSQLiteStore
    reader, writer = factory(tmp_path / "sessions.db"), factory(tmp_path / "sessions.db")
    await connection(reader)
    await connection(writer)
    yield reader, writer
    await invoke(reader, "close")
    await invoke(writer, "close")


async def read_during_replacement(reader, writer, method, args, pause_at, session_id):
    entered, release = threading.Event(), threading.Event()

    def pause(statement):
        if pause_at in statement and not entered.is_set():
            entered.set()
            assert release.wait(3)

    conn = await connection(reader)
    await invoke(conn, "set_trace_callback", pause)
    task = asyncio.create_task(invoke(reader, method, *args))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        await invoke(writer, "delete_session", session_id)
        new_session = "demo" if method == "find_session" else session_id
        await invoke(writer, "append", new_session, image_uuid="replacement", parent_id=None, branch="new")
        await invoke(writer, "set_session_cwd", new_session, "/new")
        await invoke(writer, "set_session_env", new_session, {"GENERATION": "new"})
    finally:
        release.set()
        result = await task
        await invoke(conn, "set_trace_callback", None)
    return result


@pytest.mark.parametrize(
    ("method", "pause_at"),
    [
        ("get_entry", "SELECT * FROM session_history_attachments_v1"),
        ("tip", "SELECT * FROM session_history_v1"),
        ("get_session_metadata", "SELECT key, value FROM session_env_v1"),
        ("list_branches", "SELECT branch_name FROM session_branches_v1"),
        ("find_session", "WHERE session_id LIKE"),
        ("history_dag", "SELECT * FROM session_history_attachments_v1"),
    ],
)
async def test_queries_return_the_complete_snapshot_before_concurrent_replacement(read_connections, method, pause_at):
    reader, writer = read_connections
    session_id = "app_demo" if method == "find_session" else "session"
    await invoke(writer, "append", session_id, image_uuid="original", parent_id=None)
    staged = await invoke(writer, "stage_files", session_id, [StagedFile("/input", "upload", 10, 20, 0o640)])
    await invoke(writer, "set_session_cwd", session_id, "/old")
    await invoke(writer, "set_session_env", session_id, {"GENERATION": "old"})
    args = (session_id, staged.id) if method == "get_entry" else (session_id,)
    if method == "find_session":
        args = ("demo",)
    expected = await invoke(reader, method, *args)
    actual = await read_during_replacement(reader, writer, method, args, pause_at, session_id)
    assert actual == expected
    if method == "get_entry":
        with pytest.raises(ValueError, match="not found"):
            await invoke(reader, method, *args)
    else:
        assert await invoke(reader, method, *args) != expected


async def test_read_error_rolls_back_owned_transaction(read_connections):
    reader, writer = read_connections
    await invoke(writer, "append", "session", image_uuid="base", parent_id=None)
    with pytest.raises(ValueError, match="not found"):
        await invoke(reader, "get_entry", "session", 999)
    assert not (await connection(reader)).in_transaction
    assert await invoke(reader, "delete_session", "session") is True
    await invoke(writer, "append", "session", image_uuid="new", parent_id=None)
    assert (await invoke(reader, "tip", "session")).image_uuid == "new"


async def test_nested_read_preserves_caller_write_transaction_and_rollback(read_connections):
    reader, writer = read_connections
    root = await invoke(writer, "append", "session", image_uuid="base", parent_id=None)
    conn = await connection(reader)
    await invoke(conn, "execute", "BEGIN IMMEDIATE")
    await invoke(conn, "execute", "INSERT INTO session_env_v1 VALUES ('session', 'KEY', 'uncommitted')")
    assert await invoke(reader, "get_entry", "session", root.id) == root
    assert (await invoke(reader, "get_session_metadata", "session")).env == {"KEY": "uncommitted"}
    assert conn.in_transaction
    assert (await invoke(writer, "get_session_metadata", "session")).env == {}
    with pytest.raises(ValueError, match="not found"):
        await invoke(reader, "get_entry", "session", 999)
    assert conn.in_transaction
    await invoke(conn, "rollback")
    assert (await invoke(reader, "get_session_metadata", "session")).env == {}


async def test_failed_write_after_nested_read_is_not_partially_committed(read_connections):
    reader, writer = read_connections
    root = await invoke(writer, "append", "session", image_uuid="base", parent_id=None)
    before = await invoke(reader, "read_session", "session")
    conn = await connection(reader)
    # Staging/append call get_entry within an existing write transaction.
    await invoke(
        conn,
        "execute",
        "CREATE TRIGGER fail_after_parent_read BEFORE INSERT ON session_history_v1 "
        "BEGIN SELECT RAISE(ABORT, 'write failure'); END;",
    )
    with pytest.raises(sqlite3.IntegrityError, match="write failure"):
        await invoke(reader, "append", "session", image_uuid="result", parent_id=root.id)
    assert not conn.in_transaction
    assert await invoke(writer, "read_session", "session") == before
    await invoke(conn, "execute", "DROP TRIGGER fail_after_parent_read")
    assert (await invoke(reader, "append", "session", image_uuid="result", parent_id=root.id)).parent_id == root.id


async def test_async_cancellation_during_begin_does_not_leave_transaction_open(tmp_path):
    from contree_sdk.store import AsyncSQLiteStore

    async with AsyncSQLiteStore(tmp_path / "sessions.db") as store:
        await store.append("session", image_uuid="base", parent_id=None)
        conn = await store.ensure_connection()
        entered, release = threading.Event(), threading.Event()

        def pause(statement):
            if statement == "BEGIN":
                entered.set()
                assert release.wait(3)

        await conn.set_trace_callback(pause)
        task = asyncio.create_task(store.tip("session"))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            await asyncio.sleep(0)
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            await invoke(conn, "set_trace_callback", None)
        assert not conn.in_transaction
        assert await store.delete_session("session") is True
