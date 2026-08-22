from __future__ import annotations

import os
import sqlite3
import threading
from asyncio import Lock
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contree_sdk.store.base import AsyncStore, HistoryEntry, SyncStore


try:
    import aiosqlite

    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False


DB_TIMEOUT = float(os.getenv("CONTREE_DB_TIMEOUT", "30"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS session_history_v1 (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL,
    image_uuid     TEXT NOT NULL,
    parent_id      INTEGER REFERENCES session_history_v1(id),
    kind           TEXT NOT NULL DEFAULT '',
    title          TEXT NOT NULL DEFAULT '',
    operation_uuid TEXT,
    exit_code      INTEGER,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS session_branches_v1 (
    session_id  TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    history_id  INTEGER NOT NULL REFERENCES session_history_v1(id),
    PRIMARY KEY (session_id, branch_name)
);

CREATE TABLE IF NOT EXISTS session_state_v1 (
    session_id    TEXT PRIMARY KEY,
    active_branch TEXT NOT NULL DEFAULT 'main',
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE INDEX IF NOT EXISTS ix_history_v1_session ON session_history_v1(session_id);
CREATE INDEX IF NOT EXISTS ix_history_v1_parent ON session_history_v1(parent_id);
"""


def escape_like(value: str) -> str:
    # escape SQL LIKE's own wildcards so a literal `_`/`%` in a session_id suffix
    # doesn't get treated as "match any single/any run of characters"
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def entry_from_row(row: Any) -> HistoryEntry:
    # column values are naive UTC (SQLite's strftime('%Y-%m-%dT%H:%M:%S','now')), so
    # attach tzinfo explicitly to match MemoryStore's datetime.now(timezone.utc)
    return HistoryEntry(
        id=row["id"],
        session_id=row["session_id"],
        image_uuid=row["image_uuid"],
        parent_id=row["parent_id"],
        kind=row["kind"],
        title=row["title"],
        operation_uuid=row["operation_uuid"],
        exit_code=row["exit_code"],
        created_at=datetime.fromisoformat(row["created_at"]).replace(tzinfo=timezone.utc),
    )


class SyncSQLiteStore(SyncStore):
    """SQLite-backed Store: one file holds many sessions, keyed by session_id.

    WAL journal mode + a busy timeout make the file safe to share across
    *processes*. `check_same_thread=False` plus a `threading.RLock` make one
    instance safe to share across *threads* within this process too.

    No in-place schema migrations: tables are named `session_history_v1`,
    `session_branches_v1`, `session_state_v1`. A future schema change bumps
    the suffix (`_v1` -> `_v2`, ...) instead of altering the `_v1` tables in
    place - old data under the previous suffix is abandoned, not migrated
    forward.
    """

    def __init__(self, db_path: str | Path) -> None:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), timeout=DB_TIMEOUT, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute(f"PRAGMA busy_timeout={int(DB_TIMEOUT * 1000)}")
        self.conn.executescript(SCHEMA)
        self.rlock = threading.RLock()

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        # roll back on ANY exception mid-write, so a failed write never leaves this
        # connection's next statement silently continuing inside a half-done transaction
        try:
            yield
        except BaseException:
            self.conn.rollback()
            raise

    def branch_tip_row(self, session_id: str, branch: str) -> sqlite3.Row | None:
        with self.rlock:
            return self.conn.execute(
                "SELECT history_id FROM session_branches_v1 WHERE session_id = ? AND branch_name = ?",
                (session_id, branch),
            ).fetchone()

    def get_entry_row(self, session_id: str, history_id: int) -> HistoryEntry:
        with self.rlock:
            row = self.conn.execute(
                "SELECT * FROM session_history_v1 WHERE id = ? AND session_id = ?",
                (history_id, session_id),
            ).fetchone()
        if row is None:
            raise ValueError(f"history entry {history_id} not found in session {session_id!r}")
        return entry_from_row(row)

    def get_entry(self, session_id: str, history_id: int) -> HistoryEntry:
        return self.get_entry_row(session_id, history_id)

    def active_branch(self, session_id: str) -> str | None:
        with self.rlock:
            row = self.conn.execute(
                "SELECT active_branch FROM session_state_v1 WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return row["active_branch"] if row else None

    def latest_child_id(self, session_id: str, parent_id: int) -> int | None:
        with self.rlock:
            row = self.conn.execute(
                "SELECT id FROM session_history_v1 WHERE parent_id = ? AND session_id = ? ORDER BY id DESC LIMIT 1",
                (parent_id, session_id),
            ).fetchone()
        return None if row is None else row["id"]

    def append(
        self,
        session_id: str,
        *,
        image_uuid: str,
        parent_id: int | None,
        kind: str = "",
        title: str = "",
        operation_uuid: str | None = None,
        exit_code: int | None = None,
        branch: str | None = None,
    ) -> HistoryEntry:
        with self.rlock, self.transaction():
            branch_name = branch or self.active_branch(session_id) or "main"
            cursor = self.conn.execute(
                """
                INSERT INTO session_history_v1
                    (session_id, image_uuid, parent_id, kind, title, operation_uuid, exit_code)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, image_uuid, parent_id, kind, title, operation_uuid, exit_code),
            )
            new_id = cursor.lastrowid
            if new_id is None:
                raise RuntimeError("INSERT into session_history_v1 did not report a row id")
            self.conn.execute(
                """
                INSERT INTO session_branches_v1 (session_id, branch_name, history_id)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id, branch_name) DO UPDATE SET history_id = excluded.history_id
                """,
                (session_id, branch_name, new_id),
            )
            self.conn.execute(
                """
                INSERT INTO session_state_v1 (session_id, active_branch, updated_at)
                VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%S','now'))
                ON CONFLICT(session_id) DO UPDATE SET updated_at = strftime('%Y-%m-%dT%H:%M:%S','now')
                """,
                (session_id, branch_name),
            )
            self.conn.commit()
            return self.get_entry_row(session_id, new_id)

    def tip(self, session_id: str, branch: str | None = None) -> HistoryEntry | None:
        with self.rlock:
            branch_name = branch or self.active_branch(session_id)
            if branch_name is None:
                return None
            row = self.branch_tip_row(session_id, branch_name)
            return None if row is None else self.get_entry_row(session_id, row["history_id"])

    def navigate(self, session_id: str, target: int) -> HistoryEntry:
        if target == 0:
            raise ValueError("navigation target must not be 0")
        with self.rlock, self.transaction():
            branch = self.active_branch(session_id)
            if branch is None:
                raise ValueError(f"no active session {session_id!r}")
            if target > 0:
                current_id = target
                self.get_entry_row(session_id, current_id)
            else:
                tip_row = self.branch_tip_row(session_id, branch)
                if tip_row is None:
                    raise ValueError(f"no active session {session_id!r}")
                current_id = tip_row["history_id"]
                for step in range(-target):
                    entry = self.get_entry_row(session_id, current_id)
                    if entry.parent_id is None:
                        raise ValueError(f"cannot go back {-target} steps: only {step} ancestors available")
                    current_id = entry.parent_id
            self.conn.execute(
                "UPDATE session_branches_v1 SET history_id = ? WHERE session_id = ? AND branch_name = ?",
                (current_id, session_id, branch),
            )
            self.conn.execute(
                "UPDATE session_state_v1 SET updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') WHERE session_id = ?",
                (session_id,),
            )
            self.conn.commit()
            return self.get_entry_row(session_id, current_id)

    def rollback(self, session_id: str, steps: int = 1) -> HistoryEntry:
        if steps < 1:
            raise ValueError("rollback steps must be >= 1")
        return self.navigate(session_id, -steps)

    def navigate_forward(self, session_id: str, steps: int = 1) -> HistoryEntry:
        if steps < 1:
            raise ValueError("forward steps must be >= 1")
        with self.rlock, self.transaction():
            branch = self.active_branch(session_id)
            if branch is None:
                raise ValueError(f"no active session {session_id!r}")
            tip_row = self.branch_tip_row(session_id, branch)
            if tip_row is None:
                raise ValueError(f"no active session {session_id!r}")
            current_id = tip_row["history_id"]
            for step in range(steps):
                child_id = self.latest_child_id(session_id, current_id)
                if child_id is None:
                    raise ValueError(f"cannot go forward {steps} steps: only {step} children available")
                current_id = child_id
            self.conn.execute(
                "UPDATE session_branches_v1 SET history_id = ? WHERE session_id = ? AND branch_name = ?",
                (current_id, session_id, branch),
            )
            self.conn.execute(
                "UPDATE session_state_v1 SET updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') WHERE session_id = ?",
                (session_id,),
            )
            self.conn.commit()
            return self.get_entry_row(session_id, current_id)

    def create_branch(self, session_id: str, name: str, *, from_branch: str | None = None) -> None:
        with self.rlock, self.transaction():
            source = from_branch or self.active_branch(session_id)
            if source is None:
                raise ValueError(f"no active session {session_id!r}")
            row = self.branch_tip_row(session_id, source)
            if row is None:
                raise ValueError(f"source branch {source!r} does not exist")
            existing = self.branch_tip_row(session_id, name)
            if existing is not None:
                raise ValueError(f"branch {name!r} already exists")
            self.conn.execute(
                "INSERT INTO session_branches_v1 (session_id, branch_name, history_id) VALUES (?, ?, ?)",
                (session_id, name, row["history_id"]),
            )
            self.conn.commit()

    def switch_branch(self, session_id: str, name: str) -> HistoryEntry:
        with self.rlock, self.transaction():
            row = self.branch_tip_row(session_id, name)
            if row is None:
                raise ValueError(f"branch {name!r} does not exist")
            self.conn.execute(
                "UPDATE session_state_v1 SET active_branch = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
                "WHERE session_id = ?",
                (name, session_id),
            )
            self.conn.commit()
            return self.get_entry_row(session_id, row["history_id"])

    def list_branches(self, session_id: str) -> list[tuple[str, bool]]:
        with self.rlock:
            active = self.active_branch(session_id)
            if active is None:
                return []
            rows = self.conn.execute(
                "SELECT branch_name FROM session_branches_v1 WHERE session_id = ? ORDER BY branch_name",
                (session_id,),
            ).fetchall()
            return [(row["branch_name"], row["branch_name"] == active) for row in rows]

    def delete_branch(self, session_id: str, name: str) -> None:
        with self.rlock, self.transaction():
            if name == self.active_branch(session_id):
                raise ValueError("cannot delete the active branch")
            cursor = self.conn.execute(
                "DELETE FROM session_branches_v1 WHERE session_id = ? AND branch_name = ?",
                (session_id, name),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"branch {name!r} does not exist")
            self.conn.commit()

    def list_sessions(self) -> list[str]:
        with self.rlock:
            rows = self.conn.execute("SELECT session_id FROM session_state_v1 ORDER BY session_id").fetchall()
        return [row["session_id"] for row in rows]

    def find_session(self, name: str) -> str:
        with self.rlock:
            exact = self.conn.execute(
                "SELECT session_id FROM session_state_v1 WHERE session_id = ?",
                (name,),
            ).fetchone()
            if exact is not None:
                return exact["session_id"]
            rows = self.conn.execute(
                "SELECT session_id FROM session_state_v1 WHERE session_id LIKE ? ESCAPE '\\'",
                (f"%\\_{escape_like(name)}",),
            ).fetchall()
        if not rows:
            raise ValueError(f"session {name!r} not found")
        if len(rows) > 1:
            matches = ", ".join(row["session_id"] for row in rows)
            raise ValueError(f"ambiguous session {name!r}: matches {matches}")
        return rows[0]["session_id"]

    def delete_session(self, session_id: str) -> bool:
        with self.rlock, self.transaction():
            row = self.conn.execute("SELECT 1 FROM session_state_v1 WHERE session_id = ?", (session_id,)).fetchone()
            if row is None:
                return False
            self.conn.execute("DELETE FROM session_branches_v1 WHERE session_id = ?", (session_id,))
            self.conn.execute("DELETE FROM session_history_v1 WHERE session_id = ?", (session_id,))
            self.conn.execute("DELETE FROM session_state_v1 WHERE session_id = ?", (session_id,))
            self.conn.commit()
            return True

    def history_dag(self, session_id: str) -> tuple[list[HistoryEntry], dict[int, list[str]]]:
        with self.rlock:
            rows = self.conn.execute(
                "SELECT * FROM session_history_v1 WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            entries = [entry_from_row(row) for row in rows]
            branch_rows = self.conn.execute(
                "SELECT history_id, branch_name FROM session_branches_v1 WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        branch_map: dict[int, list[str]] = {}
        for row in branch_rows:
            branch_map.setdefault(row["history_id"], []).append(row["branch_name"])
        return entries, branch_map


async def branch_tip_row_async(conn: Any, session_id: str, branch: str) -> Any:
    cursor = await conn.execute(
        "SELECT history_id FROM session_branches_v1 WHERE session_id = ? AND branch_name = ?",
        (session_id, branch),
    )
    return await cursor.fetchone()


async def get_entry_row_async(conn: Any, session_id: str, history_id: int) -> HistoryEntry:
    cursor = await conn.execute(
        "SELECT * FROM session_history_v1 WHERE id = ? AND session_id = ?",
        (history_id, session_id),
    )
    row = await cursor.fetchone()
    if row is None:
        raise ValueError(f"history entry {history_id} not found in session {session_id!r}")
    return entry_from_row(row)


async def active_branch_row_async(conn: Any, session_id: str) -> str | None:
    cursor = await conn.execute(
        "SELECT active_branch FROM session_state_v1 WHERE session_id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    return row["active_branch"] if row else None


async def latest_child_id_async(conn: Any, session_id: str, parent_id: int) -> int | None:
    cursor = await conn.execute(
        "SELECT id FROM session_history_v1 WHERE parent_id = ? AND session_id = ? ORDER BY id DESC LIMIT 1",
        (parent_id, session_id),
    )
    row = await cursor.fetchone()
    return None if row is None else row["id"]


class AsyncSQLiteStore(AsyncStore):
    """SQLite-backed Store using aiosqlite: one file holds many sessions, keyed by session_id.

    The connection opens lazily on first use, since `aiosqlite.connect()` is
    itself a coroutine and can't run in `__init__`. `lock` (an `asyncio.Lock`,
    not reentrant) serializes whole operations rather than individual
    statements - unlike `SyncSQLiteStore`'s `threading.RLock`, so internal
    helpers here never re-acquire it. Requires the `contree-sdk[async]` extra.

    No in-place schema migrations: tables are named `session_history_v1`,
    `session_branches_v1`, `session_state_v1`. A future schema change bumps
    the suffix (`_v1` -> `_v2`, ...) instead of altering the `_v1` tables in
    place - old data under the previous suffix is abandoned, not migrated
    forward.
    """

    def __init__(self, db_path: str | Path) -> None:
        if not AIOSQLITE_AVAILABLE:
            raise ImportError('AsyncSQLiteStore requires aiosqlite; install it via `pip install "contree-sdk[async]"`')
        self.db_path = Path(db_path)
        self.conn: aiosqlite.Connection | None = None
        self.connect_lock = Lock()
        self.lock = Lock()

    async def ensure_connection(self) -> aiosqlite.Connection:
        if self.conn is not None:
            return self.conn
        async with self.connect_lock:
            if self.conn is not None:
                return self.conn
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = await aiosqlite.connect(str(self.db_path), timeout=DB_TIMEOUT)
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.execute(f"PRAGMA busy_timeout={int(DB_TIMEOUT * 1000)}")
            await conn.executescript(SCHEMA)
            self.conn = conn
            return conn

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        # roll back on ANY exception mid-write (including asyncio.CancelledError, a
        # BaseException), so a cancelled/failed write never leaves this connection's
        # next statement silently continuing inside a half-done transaction
        conn = self.conn
        if conn is None:
            raise RuntimeError("transaction() requires an established connection")
        try:
            yield
        except BaseException:
            await conn.rollback()
            raise

    async def get_entry(self, session_id: str, history_id: int) -> HistoryEntry:
        conn = await self.ensure_connection()
        async with self.lock:
            return await get_entry_row_async(conn, session_id, history_id)

    async def active_branch(self, session_id: str) -> str | None:
        conn = await self.ensure_connection()
        async with self.lock:
            return await active_branch_row_async(conn, session_id)

    async def append(
        self,
        session_id: str,
        *,
        image_uuid: str,
        parent_id: int | None,
        kind: str = "",
        title: str = "",
        operation_uuid: str | None = None,
        exit_code: int | None = None,
        branch: str | None = None,
    ) -> HistoryEntry:
        conn = await self.ensure_connection()
        async with self.lock, self.transaction():
            branch_name = branch or await active_branch_row_async(conn, session_id) or "main"
            cursor = await conn.execute(
                """
                INSERT INTO session_history_v1
                    (session_id, image_uuid, parent_id, kind, title, operation_uuid, exit_code)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, image_uuid, parent_id, kind, title, operation_uuid, exit_code),
            )
            new_id = cursor.lastrowid
            if new_id is None:
                raise RuntimeError("INSERT into session_history_v1 did not report a row id")
            await conn.execute(
                """
                INSERT INTO session_branches_v1 (session_id, branch_name, history_id)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id, branch_name) DO UPDATE SET history_id = excluded.history_id
                """,
                (session_id, branch_name, new_id),
            )
            await conn.execute(
                """
                INSERT INTO session_state_v1 (session_id, active_branch, updated_at)
                VALUES (?, ?, strftime('%Y-%m-%dT%H:%M:%S','now'))
                ON CONFLICT(session_id) DO UPDATE SET updated_at = strftime('%Y-%m-%dT%H:%M:%S','now')
                """,
                (session_id, branch_name),
            )
            await conn.commit()
            return await get_entry_row_async(conn, session_id, new_id)

    async def tip(self, session_id: str, branch: str | None = None) -> HistoryEntry | None:
        conn = await self.ensure_connection()
        async with self.lock:
            branch_name = branch or await active_branch_row_async(conn, session_id)
            if branch_name is None:
                return None
            row = await branch_tip_row_async(conn, session_id, branch_name)
            return None if row is None else await get_entry_row_async(conn, session_id, row["history_id"])

    async def navigate(self, session_id: str, target: int) -> HistoryEntry:
        if target == 0:
            raise ValueError("navigation target must not be 0")
        conn = await self.ensure_connection()
        async with self.lock, self.transaction():
            branch = await active_branch_row_async(conn, session_id)
            if branch is None:
                raise ValueError(f"no active session {session_id!r}")
            if target > 0:
                current_id = target
                await get_entry_row_async(conn, session_id, current_id)
            else:
                tip_row = await branch_tip_row_async(conn, session_id, branch)
                if tip_row is None:
                    raise ValueError(f"no active session {session_id!r}")
                current_id = tip_row["history_id"]
                for step in range(-target):
                    entry = await get_entry_row_async(conn, session_id, current_id)
                    if entry.parent_id is None:
                        raise ValueError(f"cannot go back {-target} steps: only {step} ancestors available")
                    current_id = entry.parent_id
            await conn.execute(
                "UPDATE session_branches_v1 SET history_id = ? WHERE session_id = ? AND branch_name = ?",
                (current_id, session_id, branch),
            )
            await conn.execute(
                "UPDATE session_state_v1 SET updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') WHERE session_id = ?",
                (session_id,),
            )
            await conn.commit()
            return await get_entry_row_async(conn, session_id, current_id)

    async def rollback(self, session_id: str, steps: int = 1) -> HistoryEntry:
        if steps < 1:
            raise ValueError("rollback steps must be >= 1")
        return await self.navigate(session_id, -steps)

    async def navigate_forward(self, session_id: str, steps: int = 1) -> HistoryEntry:
        if steps < 1:
            raise ValueError("forward steps must be >= 1")
        conn = await self.ensure_connection()
        async with self.lock, self.transaction():
            branch = await active_branch_row_async(conn, session_id)
            if branch is None:
                raise ValueError(f"no active session {session_id!r}")
            tip_row = await branch_tip_row_async(conn, session_id, branch)
            if tip_row is None:
                raise ValueError(f"no active session {session_id!r}")
            current_id = tip_row["history_id"]
            for step in range(steps):
                child_id = await latest_child_id_async(conn, session_id, current_id)
                if child_id is None:
                    raise ValueError(f"cannot go forward {steps} steps: only {step} children available")
                current_id = child_id
            await conn.execute(
                "UPDATE session_branches_v1 SET history_id = ? WHERE session_id = ? AND branch_name = ?",
                (current_id, session_id, branch),
            )
            await conn.execute(
                "UPDATE session_state_v1 SET updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') WHERE session_id = ?",
                (session_id,),
            )
            await conn.commit()
            return await get_entry_row_async(conn, session_id, current_id)

    async def create_branch(self, session_id: str, name: str, *, from_branch: str | None = None) -> None:
        conn = await self.ensure_connection()
        async with self.lock, self.transaction():
            source = from_branch or await active_branch_row_async(conn, session_id)
            if source is None:
                raise ValueError(f"no active session {session_id!r}")
            row = await branch_tip_row_async(conn, session_id, source)
            if row is None:
                raise ValueError(f"source branch {source!r} does not exist")
            existing = await branch_tip_row_async(conn, session_id, name)
            if existing is not None:
                raise ValueError(f"branch {name!r} already exists")
            await conn.execute(
                "INSERT INTO session_branches_v1 (session_id, branch_name, history_id) VALUES (?, ?, ?)",
                (session_id, name, row["history_id"]),
            )
            await conn.commit()

    async def switch_branch(self, session_id: str, name: str) -> HistoryEntry:
        conn = await self.ensure_connection()
        async with self.lock, self.transaction():
            row = await branch_tip_row_async(conn, session_id, name)
            if row is None:
                raise ValueError(f"branch {name!r} does not exist")
            await conn.execute(
                "UPDATE session_state_v1 SET active_branch = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
                "WHERE session_id = ?",
                (name, session_id),
            )
            await conn.commit()
            return await get_entry_row_async(conn, session_id, row["history_id"])

    async def list_branches(self, session_id: str) -> list[tuple[str, bool]]:
        conn = await self.ensure_connection()
        async with self.lock:
            active = await active_branch_row_async(conn, session_id)
            if active is None:
                return []
            cursor = await conn.execute(
                "SELECT branch_name FROM session_branches_v1 WHERE session_id = ? ORDER BY branch_name",
                (session_id,),
            )
            rows = await cursor.fetchall()
            return [(row["branch_name"], row["branch_name"] == active) for row in rows]

    async def delete_branch(self, session_id: str, name: str) -> None:
        conn = await self.ensure_connection()
        async with self.lock, self.transaction():
            if name == await active_branch_row_async(conn, session_id):
                raise ValueError("cannot delete the active branch")
            cursor = await conn.execute(
                "DELETE FROM session_branches_v1 WHERE session_id = ? AND branch_name = ?",
                (session_id, name),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"branch {name!r} does not exist")
            await conn.commit()

    async def list_sessions(self) -> list[str]:
        conn = await self.ensure_connection()
        async with self.lock:
            cursor = await conn.execute("SELECT session_id FROM session_state_v1 ORDER BY session_id")
            rows = await cursor.fetchall()
        return [row["session_id"] for row in rows]

    async def find_session(self, name: str) -> str:
        conn = await self.ensure_connection()
        async with self.lock:
            cursor = await conn.execute(
                "SELECT session_id FROM session_state_v1 WHERE session_id = ?",
                (name,),
            )
            exact = await cursor.fetchone()
            if exact is not None:
                return exact["session_id"]
            cursor = await conn.execute(
                "SELECT session_id FROM session_state_v1 WHERE session_id LIKE ? ESCAPE '\\'",
                (f"%\\_{escape_like(name)}",),
            )
            rows = list(await cursor.fetchall())
        if not rows:
            raise ValueError(f"session {name!r} not found")
        if len(rows) > 1:
            matches = ", ".join(row["session_id"] for row in rows)
            raise ValueError(f"ambiguous session {name!r}: matches {matches}")
        return rows[0]["session_id"]

    async def delete_session(self, session_id: str) -> bool:
        conn = await self.ensure_connection()
        async with self.lock, self.transaction():
            cursor = await conn.execute("SELECT 1 FROM session_state_v1 WHERE session_id = ?", (session_id,))
            row = await cursor.fetchone()
            if row is None:
                return False
            await conn.execute("DELETE FROM session_branches_v1 WHERE session_id = ?", (session_id,))
            await conn.execute("DELETE FROM session_history_v1 WHERE session_id = ?", (session_id,))
            await conn.execute("DELETE FROM session_state_v1 WHERE session_id = ?", (session_id,))
            await conn.commit()
            return True

    async def history_dag(self, session_id: str) -> tuple[list[HistoryEntry], dict[int, list[str]]]:
        conn = await self.ensure_connection()
        async with self.lock:
            cursor = await conn.execute(
                "SELECT * FROM session_history_v1 WHERE session_id = ? ORDER BY id",
                (session_id,),
            )
            rows = await cursor.fetchall()
            entries = [entry_from_row(row) for row in rows]
            branch_cursor = await conn.execute(
                "SELECT history_id, branch_name FROM session_branches_v1 WHERE session_id = ?",
                (session_id,),
            )
            branch_rows = await branch_cursor.fetchall()
        branch_map: dict[int, list[str]] = {}
        for row in branch_rows:
            branch_map.setdefault(row["history_id"], []).append(row["branch_name"])
        return entries, branch_map
