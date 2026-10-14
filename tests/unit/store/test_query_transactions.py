"""History snapshots and branch cleanup remain consistent across SQLite connections."""

import asyncio
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError

import pytest

from contree_sdk.store import AsyncSQLiteStore, SyncSQLiteStore
from contree_sdk.store import sqlite as sqlite_module


def test_sync_snapshot_ignores_writes_committed_during_read(tmp_path, monkeypatch):
    path = tmp_path / "sessions.db"
    with SyncSQLiteStore(path) as reader, SyncSQLiteStore(path) as writer:
        root = writer.append("session", image_uuid="base", parent_id=None)
        writer.set_session_cwd("session", "/old")
        original = reader.history_dag

        def concurrent_update(session_id):
            writer.append(session_id, image_uuid="new", parent_id=root.id, branch="feature")
            writer.switch_branch(session_id, "feature")
            writer.set_session_cwd(session_id, "/new")
            return original(session_id)

        monkeypatch.setattr(reader, "history_dag", concurrent_update)
        snapshot = reader.read_session("session")
        assert snapshot.entries == (root,)
        assert snapshot.metadata.cwd == "/old"
        assert snapshot.summary().active_branch == "main"
        monkeypatch.setattr(reader, "history_dag", original)
        after = reader.read_session("session")
        assert len(after.entries) == 2
        assert after.metadata.cwd == "/new"
        assert after.summary().active_branch == "feature"


async def test_async_snapshot_ignores_writes_committed_during_read(tmp_path, monkeypatch):
    path = tmp_path / "sessions.db"
    async with AsyncSQLiteStore(path) as reader, AsyncSQLiteStore(path) as writer:
        root = await writer.append("session", image_uuid="base", parent_id=None)
        await writer.set_session_cwd("session", "/old")
        original = sqlite_module.history_dag_async

        async def concurrent_update(conn, session_id):
            await writer.append(session_id, image_uuid="new", parent_id=root.id, branch="feature")
            await writer.switch_branch(session_id, "feature")
            await writer.set_session_cwd(session_id, "/new")
            return await original(conn, session_id)

        monkeypatch.setattr(sqlite_module, "history_dag_async", concurrent_update)
        snapshot = await reader.read_session("session")
        assert snapshot.entries == (root,)
        assert snapshot.metadata.cwd == "/old"
        assert snapshot.summary().active_branch == "main"
        monkeypatch.setattr(sqlite_module, "history_dag_async", original)
        after = await reader.read_session("session")
        assert len(after.entries) == 2
        assert after.metadata.cwd == "/new"
        assert after.summary().active_branch == "feature"


FAIL_DELETE = """
CREATE TRIGGER fail_second_delete BEFORE DELETE ON session_branches_v1
WHEN OLD.branch_name = 'svc:z'
BEGIN SELECT RAISE(ABORT, 'delete failed'); END;
"""


def test_sync_prune_rolls_back_all_deletions_on_failure(tmp_path):
    with SyncSQLiteStore(tmp_path / "sessions.db") as store:
        store.append("session", image_uuid="base", parent_id=None)
        store.create_branch("session", "svc:a")
        store.create_branch("session", "svc:z")
        before = store.read_session("session")
        store.conn.execute(FAIL_DELETE)
        with pytest.raises(sqlite3.IntegrityError, match="delete failed"):
            store.prune_branches("session", prefix="svc:")
        assert store.read_session("session") == before
        store.conn.execute("DROP TRIGGER fail_second_delete")
        assert store.prune_branches("session", prefix="svc:") == ("svc:a", "svc:z")


async def test_async_prune_rolls_back_all_deletions_on_failure(tmp_path):
    async with AsyncSQLiteStore(tmp_path / "sessions.db") as store:
        await store.append("session", image_uuid="base", parent_id=None)
        await store.create_branch("session", "svc:a")
        await store.create_branch("session", "svc:z")
        before = await store.read_session("session")
        conn = await store.ensure_connection()
        await conn.execute(FAIL_DELETE)
        with pytest.raises(sqlite3.IntegrityError, match="delete failed"):
            await store.prune_branches("session", prefix="svc:")
        assert await store.read_session("session") == before
        await conn.execute("DROP TRIGGER fail_second_delete")
        assert await store.prune_branches("session", prefix="svc:") == ("svc:a", "svc:z")


def test_sync_switch_and_prune_cannot_leave_an_active_branch_missing(tmp_path, monkeypatch):
    path = tmp_path / "sessions.db"
    with SyncSQLiteStore(path) as switching, SyncSQLiteStore(path) as pruning, ThreadPoolExecutor(2) as pool:
        switching.append("session", image_uuid="base", parent_id=None)
        switching.create_branch("session", "svc:selected")
        switching.create_branch("session", "svc:old")
        entered = threading.Event()
        release = threading.Event()
        prune_started = threading.Event()
        original = switching.branch_tip_row

        def paused_read(*args):
            result = original(*args)
            entered.set()
            assert release.wait(3)
            return result

        def prune():
            prune_started.set()
            return pruning.prune_branches("session", prefix="svc:")

        monkeypatch.setattr(switching, "branch_tip_row", paused_read)
        switch = pool.submit(switching.switch_branch, "session", "svc:selected")
        try:
            assert entered.wait(2)
            removal = pool.submit(prune)
            assert prune_started.wait(2)
            with pytest.raises(FutureTimeoutError):
                removal.result(timeout=0.02)
        finally:
            release.set()
        switch.result(timeout=2)
        assert removal.result(timeout=2) == ("svc:old",)
        assert pruning.read_session("session").summary().active_branch == "svc:selected"


async def test_async_switch_and_prune_cannot_leave_an_active_branch_missing(tmp_path, monkeypatch):
    path = tmp_path / "sessions.db"
    async with AsyncSQLiteStore(path) as switching, AsyncSQLiteStore(path) as pruning:
        await switching.append("session", image_uuid="base", parent_id=None)
        await switching.create_branch("session", "svc:selected")
        await switching.create_branch("session", "svc:old")
        await pruning.ensure_connection()
        entered = asyncio.Event()
        release = asyncio.Event()
        original = sqlite_module.branch_tip_row_async

        async def paused_read(*args):
            result = await original(*args)
            entered.set()
            await asyncio.wait_for(release.wait(), 3)
            return result

        monkeypatch.setattr(sqlite_module, "branch_tip_row_async", paused_read)
        switch = asyncio.create_task(switching.switch_branch("session", "svc:selected"))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            removal = asyncio.create_task(pruning.prune_branches("session", prefix="svc:"))
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(removal), 0.02)
        finally:
            release.set()
        await asyncio.wait_for(switch, 2)
        assert await asyncio.wait_for(removal, 2) == ("svc:old",)
        assert (await pruning.read_session("session")).summary().active_branch == "svc:selected"
