from __future__ import annotations

import os
import sqlite3
import threading
from asyncio import to_thread
from datetime import datetime
from pathlib import Path

from contree_sdk.store.base import HistoryEntry, Store


DB_TIMEOUT = float(os.getenv("CONTREE_DB_TIMEOUT", "30"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS session_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL,
    image_uuid     TEXT NOT NULL,
    parent_id      INTEGER REFERENCES session_history(id),
    kind           TEXT NOT NULL DEFAULT '',
    title          TEXT NOT NULL DEFAULT '',
    operation_uuid TEXT,
    exit_code      INTEGER,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE TABLE IF NOT EXISTS session_branches (
    session_id  TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    history_id  INTEGER NOT NULL REFERENCES session_history(id),
    PRIMARY KEY (session_id, branch_name)
);

CREATE TABLE IF NOT EXISTS session_state (
    session_id    TEXT PRIMARY KEY,
    active_branch TEXT NOT NULL DEFAULT 'main',
    updated_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S','now'))
);

CREATE INDEX IF NOT EXISTS ix_history_session ON session_history(session_id);
CREATE INDEX IF NOT EXISTS ix_history_parent ON session_history(parent_id);
"""


def entry_from_row(row: sqlite3.Row) -> HistoryEntry:
    return HistoryEntry(
        id=row["id"],
        session_id=row["session_id"],
        image_uuid=row["image_uuid"],
        parent_id=row["parent_id"],
        kind=row["kind"],
        title=row["title"],
        operation_uuid=row["operation_uuid"],
        exit_code=row["exit_code"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


class SQLiteStore(Store):
    """SQLite-backed Store: one file holds many sessions, keyed by session_id.

    WAL journal mode + a busy timeout make the file safe to share across
    *processes*. Within this process, every async method hands its blocking
    work to `asyncio.to_thread`, which may run each call on a different
    worker thread - the connection is opened with `check_same_thread=False`
    to allow that, and `rlock` (a real `threading.RLock`, not an
    `asyncio.Lock`, since worker threads are plain OS threads, not
    coroutines) serializes actual access to it across those threads.
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

    def branch_tip_row(self, session_id: str, branch: str) -> sqlite3.Row | None:
        with self.rlock:
            return self.conn.execute(
                "SELECT history_id FROM session_branches WHERE session_id = ? AND branch_name = ?",
                (session_id, branch),
            ).fetchone()

    def get_entry_row(self, session_id: str, history_id: int) -> HistoryEntry:
        with self.rlock:
            row = self.conn.execute(
                "SELECT * FROM session_history WHERE id = ? AND session_id = ?",
                (history_id, session_id),
            ).fetchone()
        if row is None:
            raise ValueError(f"history entry {history_id} not found in session {session_id!r}")
        return entry_from_row(row)

    def active_branch_sync(self, session_id: str) -> str | None:
        with self.rlock:
            row = self.conn.execute(
                "SELECT active_branch FROM session_state WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        return row["active_branch"] if row else None

    def latest_child_id(self, session_id: str, parent_id: int) -> int | None:
        with self.rlock:
            row = self.conn.execute(
                "SELECT id FROM session_history WHERE parent_id = ? AND session_id = ? ORDER BY id DESC LIMIT 1",
                (parent_id, session_id),
            ).fetchone()
        return None if row is None else row["id"]

    def append_sync(
        self,
        session_id: str,
        *,
        image_uuid: str,
        parent_id: int | None,
        kind: str,
        title: str,
        operation_uuid: str | None,
        exit_code: int | None,
        branch: str | None,
    ) -> HistoryEntry:
        with self.rlock:
            branch_name = branch or self.active_branch_sync(session_id) or "main"
            cursor = self.conn.execute(
                """
                INSERT INTO session_history
                    (session_id, image_uuid, parent_id, kind, title, operation_uuid, exit_code)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (session_id, image_uuid, parent_id, kind, title, operation_uuid, exit_code),
            )
            new_id = cursor.lastrowid
            if new_id is None:
                raise RuntimeError("INSERT into session_history did not report a row id")
            self.conn.execute(
                """
                INSERT INTO session_branches (session_id, branch_name, history_id)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id, branch_name) DO UPDATE SET history_id = excluded.history_id
                """,
                (session_id, branch_name, new_id),
            )
            self.conn.execute(
                """
                INSERT INTO session_state (session_id, active_branch, updated_at)
                VALUES (?, 'main', strftime('%Y-%m-%dT%H:%M:%S','now'))
                ON CONFLICT(session_id) DO UPDATE SET updated_at = strftime('%Y-%m-%dT%H:%M:%S','now')
                """,
                (session_id,),
            )
            self.conn.commit()
            return self.get_entry_row(session_id, new_id)

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
        return await to_thread(
            self.append_sync,
            session_id,
            image_uuid=image_uuid,
            parent_id=parent_id,
            kind=kind,
            title=title,
            operation_uuid=operation_uuid,
            exit_code=exit_code,
            branch=branch,
        )

    async def get_entry(self, session_id: str, history_id: int) -> HistoryEntry:
        return await to_thread(self.get_entry_row, session_id, history_id)

    def tip_sync(self, session_id: str, branch: str | None) -> HistoryEntry | None:
        with self.rlock:
            branch_name = branch or self.active_branch_sync(session_id)
            if branch_name is None:
                return None
            row = self.branch_tip_row(session_id, branch_name)
            return None if row is None else self.get_entry_row(session_id, row["history_id"])

    async def tip(self, session_id: str, branch: str | None = None) -> HistoryEntry | None:
        return await to_thread(self.tip_sync, session_id, branch)

    def navigate_sync(self, session_id: str, target: int) -> HistoryEntry:
        if target == 0:
            raise ValueError("navigation target must not be 0")
        with self.rlock:
            branch = self.active_branch_sync(session_id)
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
                "UPDATE session_branches SET history_id = ? WHERE session_id = ? AND branch_name = ?",
                (current_id, session_id, branch),
            )
            self.conn.execute(
                "UPDATE session_state SET updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') WHERE session_id = ?",
                (session_id,),
            )
            self.conn.commit()
            return self.get_entry_row(session_id, current_id)

    async def navigate(self, session_id: str, target: int) -> HistoryEntry:
        return await to_thread(self.navigate_sync, session_id, target)

    async def rollback(self, session_id: str, steps: int = 1) -> HistoryEntry:
        if steps < 1:
            raise ValueError("rollback steps must be >= 1")
        return await self.navigate(session_id, -steps)

    def navigate_forward_sync(self, session_id: str, steps: int) -> HistoryEntry:
        if steps < 1:
            raise ValueError("forward steps must be >= 1")
        with self.rlock:
            branch = self.active_branch_sync(session_id)
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
                "UPDATE session_branches SET history_id = ? WHERE session_id = ? AND branch_name = ?",
                (current_id, session_id, branch),
            )
            self.conn.execute(
                "UPDATE session_state SET updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') WHERE session_id = ?",
                (session_id,),
            )
            self.conn.commit()
            return self.get_entry_row(session_id, current_id)

    async def navigate_forward(self, session_id: str, steps: int = 1) -> HistoryEntry:
        return await to_thread(self.navigate_forward_sync, session_id, steps)

    def create_branch_sync(self, session_id: str, name: str, from_branch: str | None) -> None:
        with self.rlock:
            source = from_branch or self.active_branch_sync(session_id)
            if source is None:
                raise ValueError(f"no active session {session_id!r}")
            row = self.branch_tip_row(session_id, source)
            if row is None:
                raise ValueError(f"source branch {source!r} does not exist")
            existing = self.branch_tip_row(session_id, name)
            if existing is not None:
                raise ValueError(f"branch {name!r} already exists")
            self.conn.execute(
                "INSERT INTO session_branches (session_id, branch_name, history_id) VALUES (?, ?, ?)",
                (session_id, name, row["history_id"]),
            )
            self.conn.commit()

    async def create_branch(self, session_id: str, name: str, *, from_branch: str | None = None) -> None:
        await to_thread(self.create_branch_sync, session_id, name, from_branch)

    def switch_branch_sync(self, session_id: str, name: str) -> HistoryEntry:
        with self.rlock:
            row = self.branch_tip_row(session_id, name)
            if row is None:
                raise ValueError(f"branch {name!r} does not exist")
            self.conn.execute(
                "UPDATE session_state SET active_branch = ?, updated_at = strftime('%Y-%m-%dT%H:%M:%S','now') "
                "WHERE session_id = ?",
                (name, session_id),
            )
            self.conn.commit()
            return self.get_entry_row(session_id, row["history_id"])

    async def switch_branch(self, session_id: str, name: str) -> HistoryEntry:
        return await to_thread(self.switch_branch_sync, session_id, name)

    def list_branches_sync(self, session_id: str) -> list[tuple[str, bool]]:
        with self.rlock:
            active = self.active_branch_sync(session_id)
            if active is None:
                return []
            rows = self.conn.execute(
                "SELECT branch_name FROM session_branches WHERE session_id = ? ORDER BY branch_name",
                (session_id,),
            ).fetchall()
            return [(row["branch_name"], row["branch_name"] == active) for row in rows]

    async def list_branches(self, session_id: str) -> list[tuple[str, bool]]:
        return await to_thread(self.list_branches_sync, session_id)

    def delete_branch_sync(self, session_id: str, name: str) -> None:
        with self.rlock:
            if name == self.active_branch_sync(session_id):
                raise ValueError("cannot delete the active branch")
            cursor = self.conn.execute(
                "DELETE FROM session_branches WHERE session_id = ? AND branch_name = ?",
                (session_id, name),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"branch {name!r} does not exist")
            self.conn.commit()

    async def delete_branch(self, session_id: str, name: str) -> None:
        await to_thread(self.delete_branch_sync, session_id, name)

    async def active_branch(self, session_id: str) -> str | None:
        return await to_thread(self.active_branch_sync, session_id)

    def list_sessions_sync(self) -> list[str]:
        with self.rlock:
            rows = self.conn.execute("SELECT session_id FROM session_state ORDER BY session_id").fetchall()
        return [row["session_id"] for row in rows]

    async def list_sessions(self) -> list[str]:
        return await to_thread(self.list_sessions_sync)

    def find_session_sync(self, name: str) -> str:
        with self.rlock:
            rows = self.conn.execute(
                "SELECT session_id FROM session_state WHERE session_id LIKE ?",
                (f"%_{name}",),
            ).fetchall()
            if not rows:
                rows = self.conn.execute(
                    "SELECT session_id FROM session_state WHERE session_id = ?",
                    (name,),
                ).fetchall()
        if not rows:
            raise ValueError(f"session {name!r} not found")
        if len(rows) > 1:
            matches = ", ".join(row["session_id"] for row in rows)
            raise ValueError(f"ambiguous session {name!r}: matches {matches}")
        return rows[0]["session_id"]

    async def find_session(self, name: str) -> str:
        return await to_thread(self.find_session_sync, name)

    def delete_session_sync(self, session_id: str) -> bool:
        with self.rlock:
            row = self.conn.execute("SELECT 1 FROM session_state WHERE session_id = ?", (session_id,)).fetchone()
            if row is None:
                return False
            self.conn.execute("DELETE FROM session_branches WHERE session_id = ?", (session_id,))
            self.conn.execute("DELETE FROM session_history WHERE session_id = ?", (session_id,))
            self.conn.execute("DELETE FROM session_state WHERE session_id = ?", (session_id,))
            self.conn.commit()
            return True

    async def delete_session(self, session_id: str) -> bool:
        return await to_thread(self.delete_session_sync, session_id)

    def history_dag_sync(self, session_id: str) -> tuple[list[HistoryEntry], dict[int, list[str]]]:
        with self.rlock:
            rows = self.conn.execute(
                "SELECT * FROM session_history WHERE session_id = ? ORDER BY id",
                (session_id,),
            ).fetchall()
            entries = [entry_from_row(row) for row in rows]
            branch_rows = self.conn.execute(
                "SELECT history_id, branch_name FROM session_branches WHERE session_id = ?",
                (session_id,),
            ).fetchall()
        branch_map: dict[int, list[str]] = {}
        for row in branch_rows:
            branch_map.setdefault(row["history_id"], []).append(row["branch_name"])
        return entries, branch_map

    async def history_dag(self, session_id: str) -> tuple[list[HistoryEntry], dict[int, list[str]]]:
        return await to_thread(self.history_dag_sync, session_id)
