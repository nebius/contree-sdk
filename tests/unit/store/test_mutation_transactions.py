"""Mutating SQLite calls serialize across connections, including their returned values."""

import asyncio
import inspect
import sqlite3
import threading

import pytest

from contree_sdk.store import AsyncSQLiteStore, StagedFile, SyncSQLiteStore
from contree_sdk.store import sqlite as sqlite_module


async def invoke(target, method, *args, **kwargs):
    function = getattr(target, method)
    if inspect.iscoroutinefunction(function):
        return await function(*args, **kwargs)
    result = await asyncio.to_thread(function, *args, **kwargs)
    return await result if inspect.isawaitable(result) else result


@pytest.fixture(params=[SyncSQLiteStore, AsyncSQLiteStore])
async def connections(request, tmp_path):
    path = tmp_path / "sessions.db"
    first, second = request.param(path), request.param(path)
    if isinstance(first, AsyncSQLiteStore):
        await first.ensure_connection()
        await second.ensure_connection()
    yield first, second, path
    await invoke(first, "close")
    await invoke(second, "close")


async def connection(store):
    return await store.ensure_connection() if isinstance(store, AsyncSQLiteStore) else store.conn


async def seed(store):
    root = await invoke(store, "append", "session", image_uuid="root", parent_id=None)
    middle = await invoke(store, "append", "session", image_uuid="middle", parent_id=root.id)
    tip = await invoke(store, "append", "session", image_uuid="tip", parent_id=middle.id)
    return root, middle, tip


async def paused_race(first, second, query, first_method, first_args, second_method, second_args):
    entered, release, competing = threading.Event(), threading.Event(), threading.Event()

    def pause(statement):
        if query in statement and not entered.is_set():
            entered.set()
            if not release.wait(3):
                raise TimeoutError("test release was not signalled")

    def notice(statement):
        if statement.startswith("BEGIN IMMEDIATE"):
            competing.set()

    one, two = await connection(first), await connection(second)
    await invoke(one, "set_trace_callback", pause)
    await invoke(two, "set_trace_callback", notice)
    tasks = [asyncio.create_task(invoke(first, first_method, "session", *first_args))]
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        tasks.append(asyncio.create_task(invoke(second, second_method, "session", *second_args)))
        assert await asyncio.to_thread(competing.wait, 2)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(tasks[1]), 0.02)
    finally:
        release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        await invoke(one, "set_trace_callback", None)
        await invoke(two, "set_trace_callback", None)
    for result in results:
        if isinstance(result, BaseException):
            raise result
    return results


@pytest.mark.parametrize("direction", ["back", "forward"])
async def test_concurrent_navigation_moves_two_steps(connections, direction):
    first, second, _ = connections
    root, middle, tip = await seed(first)
    if direction == "forward":
        await invoke(first, "navigate", "session", root.id)
        method, args, expected = "navigate_forward", (), tip
    else:
        method, args, expected = "navigate", (-1,), root
    results = await paused_race(
        first,
        second,
        "SELECT history_id FROM session_branches_v1",
        method,
        args,
        method,
        args,
    )
    assert results == [middle, expected]
    assert await invoke(first, "tip", "session") == expected


async def test_create_branch_cannot_leave_pointer_after_session_deletion(connections):
    first, second, path = connections
    await seed(first)
    results = await paused_race(
        first,
        second,
        "SELECT history_id FROM session_branches_v1",
        "create_branch",
        ("feature",),
        "delete_session",
        (),
    )
    assert results == [None, True]
    assert await invoke(first, "list_sessions") == []
    with sqlite3.connect(path) as reader:
        assert reader.execute("SELECT * FROM session_branches_v1").fetchall() == []


async def test_only_one_concurrent_delete_reports_removal(connections):
    first, second, _ = connections
    await seed(first)
    results = await paused_race(
        first,
        second,
        "SELECT 1 FROM session_state_v1",
        "delete_session",
        (),
        "delete_session",
        (),
    )
    assert results == [True, False]
    # Both connections released their transactions, including the missing-session path.
    await seed(first)
    assert await invoke(second, "delete_session", "session") is True


async def pause_entry_reads(store, monkeypatch, pause):
    if isinstance(store, SyncSQLiteStore):
        original_sync = store.get_entry_row

        def paused_read(session_id, history_id):
            pause(history_id)
            return original_sync(session_id, history_id)

        monkeypatch.setattr(store, "get_entry_row", paused_read)
    else:
        original_async = sqlite_module.get_entry_row_async
        first_conn = await store.ensure_connection()

        async def paused_read(conn, session_id, history_id):
            if conn is first_conn:
                await asyncio.to_thread(pause, history_id)
            return await original_async(conn, session_id, history_id)

        monkeypatch.setattr(sqlite_module, "get_entry_row_async", paused_read)


@pytest.mark.parametrize("method", ["append", "navigate", "navigate_forward", "switch_branch"])
async def test_returned_entry_is_read_before_writer_lock_is_released(connections, monkeypatch, method):
    first, second, _ = connections
    root, middle, tip = await seed(first)
    await invoke(first, "create_branch", "session", "feature")
    if method == "navigate_forward":
        await invoke(first, "navigate", "session", root.id)
    entered, release, competing = threading.Event(), threading.Event(), threading.Event()
    expected_id = {"append": tip.id + 1, "navigate": middle.id, "navigate_forward": middle.id, "switch_branch": tip.id}[
        method
    ]

    def pause(history_id):
        if history_id == expected_id and not entered.is_set():
            entered.set()
            assert release.wait(3)

    await pause_entry_reads(first, monkeypatch, pause)

    def notice(statement):
        if statement.startswith("BEGIN IMMEDIATE"):
            competing.set()

    await invoke(await connection(second), "set_trace_callback", notice)
    args = {"append": (), "navigate": (-1,), "navigate_forward": (), "switch_branch": ("feature",)}[method]
    tasks = [
        asyncio.create_task(
            invoke(
                first,
                method,
                "session",
                *args,
                **({"image_uuid": "new", "parent_id": tip.id} if method == "append" else {}),
            )
        )
    ]
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        tasks.append(asyncio.create_task(invoke(second, "delete_session", "session")))
        assert await asyncio.to_thread(competing.wait, 2)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(tasks[1]), 0.02)
    finally:
        release.set()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        await invoke(await connection(second), "set_trace_callback", None)
    entry = results[0]
    if isinstance(entry, BaseException):
        raise entry
    assert entry.id == expected_id
    assert results[1] is True
    assert await invoke(second, "list_sessions") == []


@pytest.mark.parametrize("action", ["navigate", "create_branch", "delete_session"])
async def test_sql_error_rolls_back_entire_mutation_and_releases_lock(connections, action):
    first, second, path = connections
    root, _, tip = await seed(first)
    await invoke(first, "stage_files", "session", [StagedFile("/input", "upload")])
    await invoke(first, "set_session_cwd", "session", "/work")
    await invoke(first, "set_session_env", "session", {"KEY": "value"})
    before = await invoke(first, "read_session", "session")
    statement = {
        "navigate": "UPDATE ON session_state_v1",
        "create_branch": "INSERT ON session_branches_v1",
        "delete_session": "DELETE ON session_state_v1",
    }[action]
    with sqlite3.connect(path) as fault:
        fault.execute(f"CREATE TRIGGER fail_write BEFORE {statement} BEGIN SELECT RAISE(ABORT, 'write failed'); END;")
    args = {"navigate": (root.id,), "create_branch": ("feature",), "delete_session": ()}[action]
    with pytest.raises(sqlite3.IntegrityError, match="write failed"):
        await invoke(first, action, "session", *args)
    assert await invoke(second, "read_session", "session") == before
    with sqlite3.connect(path) as fault:
        fault.execute("DROP TRIGGER fail_write")
    assert await invoke(second, "navigate", "session", tip.id) == tip
    assert await invoke(first, "delete_session", "session") is True
