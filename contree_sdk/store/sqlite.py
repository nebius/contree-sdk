"""SQLite tree stores. Transactions protect invariants across connections."""

from __future__ import annotations

import json
import sqlite3
import time
from asyncio import Lock, shield
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from functools import partial
from pathlib import Path
from threading import RLock

from contree_sdk.store.base import AsyncStore, SyncStore
from contree_sdk.store.tree import (
    DEFAULT_PAGE_SIZE,
    Node,
    NodeConflictError,
    Page,
    SessionInfo,
    cursor_position,
    encode_data,
    next_cursor,
    validate_node_ids,
)
from contree_sdk.store.ttl import Clock, expiration


SCHEMA = (
    "CREATE TABLE IF NOT EXISTS tree_sessions (id TEXT PRIMARY KEY, kind TEXT NOT NULL, created "
    "REAL NOT NULL, expires REAL)",
    "CREATE TABLE IF NOT EXISTS tree_nodes (session_id TEXT NOT NULL REFERENCES "
    "tree_sessions(id) ON DELETE CASCADE, id TEXT NOT NULL, parent TEXT, kind TEXT NOT NULL, "
    "data TEXT NOT NULL, PRIMARY KEY(session_id,id), FOREIGN KEY(session_id,parent) REFERENCES "
    "tree_nodes(session_id,id))",
    "CREATE UNIQUE INDEX IF NOT EXISTS tree_root ON tree_nodes(session_id) WHERE parent IS NULL",
    "CREATE INDEX IF NOT EXISTS tree_children ON tree_nodes(session_id,parent,kind,id)",
    "CREATE INDEX IF NOT EXISTS tree_kind ON tree_sessions(kind,id)",
    "CREATE INDEX IF NOT EXISTS tree_node_kind ON tree_nodes(session_id,kind,id)",
    "CREATE INDEX IF NOT EXISTS tree_parent ON tree_nodes(session_id,parent,id)",
)


# Store-issued cursors retain the next ancestor; they are positions, not access tokens.
HISTORY_SQL = """
WITH RECURSIVE ancestry(id,parent,kind,data,depth) AS (
    SELECT id,parent,kind,data,0 FROM tree_nodes WHERE session_id=? AND id=?
    UNION ALL
    SELECT n.id,n.parent,n.kind,n.data,a.depth+1
    FROM tree_nodes AS n JOIN ancestry AS a ON n.id=a.parent
    WHERE n.session_id=? LIMIT ?
)
SELECT id,parent,kind,data FROM ancestry ORDER BY depth
"""
SQL_BATCH_SIZE = 900  # Leave room below SQLite's historical 999-parameter limit.


def sessions_query(kind: str | None, prefix: str, after: str, now: float, limit: int) -> tuple[str, tuple]:
    sql = "SELECT id,kind,created,expires FROM tree_sessions WHERE id>? AND (expires IS NULL OR expires>?)"
    args: list = [after, now]
    if kind is not None:
        sql += " AND kind=?"
        args.append(kind)
    if prefix:
        sql += " AND id>=? AND substr(id,1,length(?))=?"
        args.extend((prefix, prefix, prefix))
    return sql + " ORDER BY id LIMIT ?", (*args, limit + 1)


def nodes_query(
    session_id: str, parent_id: str | None, children: bool, kind: str | None, after: str, limit: int
) -> tuple[str, tuple]:
    sql = "SELECT id,parent,kind,data FROM tree_nodes WHERE session_id=? AND id>?"
    args: list = [session_id, after]
    if children:
        sql += " AND parent IS ?"
        args.append(parent_id)
    if kind is not None:
        sql += " AND kind=?"
        args.append(kind)
    return sql + " ORDER BY id LIMIT ?", (*args, limit + 1)


def batch_query(session_id: str, node_ids: tuple[str, ...]) -> tuple[str, tuple]:
    placeholders = ",".join("?" for _ in node_ids)
    # Only placeholder syntax is interpolated; identities remain SQL parameters.
    sql = "SELECT id,parent,kind,data FROM tree_nodes WHERE session_id=? AND id IN (" + placeholders + ")"  # noqa: S608
    return sql, (session_id, *node_ids)


def node_from_row(row: tuple) -> Node:
    return Node(id=row[0], parent_id=row[1], kind=row[2], data=json.loads(row[3]))


class SyncSQLiteStore(SyncStore):
    """Persist trees. None TTL means no expiry for this implementation."""

    def __init__(self, db_path: str | Path, *, clock: Clock = time.time) -> None:
        self.db_path = str(db_path)
        self.clock = clock
        self.lock = RLock()
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, isolation_level=None, check_same_thread=False, timeout=30)
        self.conn.execute("PRAGMA foreign_keys=ON")
        for statement in SCHEMA:
            self.conn.execute(statement)

    def _rows(self, sql: str, args: tuple = ()) -> list[tuple]:
        return self.conn.execute(sql, args).fetchall()

    def _write(self, sql: str, args: tuple = ()) -> None:
        self.conn.execute(sql, args)

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[None]:
        with self.lock:
            self.conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            try:
                yield
                self.conn.commit()
            except BaseException:
                self.conn.rollback()
                raise

    def _info(self, session_id: str) -> SessionInfo | None:
        rows = self._rows(
            "SELECT id,kind,created,expires FROM tree_sessions WHERE id=? AND (expires IS NULL OR expires>?)",
            (session_id, self.clock()),
        )
        return SessionInfo(*rows[0]) if rows else None

    def _require(self, session_id: str) -> SessionInfo:
        info = self._info(session_id)
        if info is None:
            raise ValueError(f"unknown or expired session {session_id!r}")
        return info

    def create_session(self, session_id: str, *, kind: str = "session", ttl: float | None = None) -> SessionInfo:
        if not isinstance(session_id, str) or not session_id or not isinstance(kind, str) or not kind:
            raise ValueError("session_id and kind must be nonempty strings")
        now = self.clock()
        expires = expiration(ttl, now)
        with self._transaction(write=True):
            existing = self._info(session_id)
            if existing is not None:
                if existing.kind != kind:
                    raise ValueError("session already exists with another kind")
                return existing
            self._write("DELETE FROM tree_sessions WHERE id=?", (session_id,))
            self._write("INSERT INTO tree_sessions VALUES (?,?,?,?)", (session_id, kind, now, expires))
            return SessionInfo(session_id, kind, now, expires)

    def get_session(self, session_id: str) -> SessionInfo | None:
        with self._transaction():
            return self._info(session_id)

    def set_session_ttl(self, session_id: str, ttl: float | None) -> SessionInfo:
        expires = expiration(ttl, self.clock())
        with self._transaction(write=True):
            info = self._require(session_id)
            self._write("UPDATE tree_sessions SET expires=? WHERE id=?", (expires, session_id))
            return SessionInfo(info.session_id, info.kind, info.created_at, expires)

    def delete_session(self, session_id: str) -> bool:
        with self._transaction(write=True):
            found = bool(self._rows("SELECT id FROM tree_sessions WHERE id=?", (session_id,)))
            self._write("DELETE FROM tree_sessions WHERE id=?", (session_id,))
            return found

    def list_sessions(
        self, *, kind: str | None = None, prefix: str = "", limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[SessionInfo]:
        scope = ("sessions", kind, prefix)
        after = cursor_position(cursor, scope, limit) or ""
        with self._transaction():
            rows = self._rows(*sessions_query(kind, prefix, after, self.clock(), limit))
            items = tuple(SessionInfo(*row) for row in rows[:limit])
            return Page(items, next_cursor(scope, items[-1].session_id) if len(rows) > limit else None)

    def append(self, session_id: str, node: Node) -> None:
        payload = encode_data(node.data)
        with self._transaction(write=True):
            self._require(session_id)
            rows = self._rows(
                "SELECT id,parent,kind,data FROM tree_nodes WHERE session_id=? AND id=?", (session_id, node.id)
            )
            if rows:
                if rows[0] != (node.id, node.parent_id, node.kind, payload):
                    raise NodeConflictError("node identity already has different contents")
                return
            if node.parent_id is None:
                if self._rows("SELECT id FROM tree_nodes WHERE session_id=? AND parent IS NULL", (session_id,)):
                    raise NodeConflictError("tree already has a root")
            elif not self._rows("SELECT id FROM tree_nodes WHERE session_id=? AND id=?", (session_id, node.parent_id)):
                raise ValueError("parent does not exist in this session")
            self._write(
                "INSERT INTO tree_nodes VALUES (?,?,?,?,?)", (session_id, node.id, node.parent_id, node.kind, payload)
            )

    def _node(self, session_id: str, node_id: str) -> Node:
        rows = self._rows(
            "SELECT id,parent,kind,data FROM tree_nodes WHERE session_id=? AND id=?", (session_id, node_id)
        )
        if not rows:
            raise ValueError(f"unknown node {node_id!r}")
        return node_from_row(rows[0])

    def get_node(self, session_id: str, node_id: str) -> Node:
        with self._transaction():
            self._require(session_id)
            return self._node(session_id, node_id)

    def get_nodes(self, session_id: str, node_ids: tuple[str, ...]) -> tuple[Node | None, ...]:
        validate_node_ids(node_ids)
        with self._transaction():
            self._require(session_id)
            found = {}
            for start in range(0, len(node_ids), SQL_BATCH_SIZE):
                rows = self._rows(*batch_query(session_id, node_ids[start : start + SQL_BATCH_SIZE]))
                found.update((row[0], row) for row in rows)
            return tuple(node_from_row(found[node_id]) if node_id in found else None for node_id in node_ids)

    def list_nodes(
        self, session_id: str, *, kind: str | None = None, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Node]:
        return self._list_nodes(session_id, None, False, kind, limit, cursor)

    def list_children(
        self,
        session_id: str,
        parent_id: str | None,
        *,
        kind: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[Node]:
        return self._list_nodes(session_id, parent_id, True, kind, limit, cursor)

    def _list_nodes(
        self, session_id: str, parent_id: str | None, children: bool, kind: str | None, limit: int, cursor: str | None
    ) -> Page[Node]:
        scope = ("nodes", session_id, parent_id, children, kind)
        after = cursor_position(cursor, scope, limit) or ""
        with self._transaction():
            self._require(session_id)
            if children and parent_id is not None:
                self._node(session_id, parent_id)
            rows = self._rows(*nodes_query(session_id, parent_id, children, kind, after, limit))
            items = tuple(node_from_row(row) for row in rows[:limit])
            return Page(items, next_cursor(scope, items[-1].id) if len(rows) > limit else None)

    def list_history(
        self, session_id: str, from_node: str, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Node]:
        scope = ("history", session_id, from_node)
        with self._transaction():
            position = cursor_position(cursor, scope, limit) or from_node
            self._require(session_id)
            rows = self._rows(HISTORY_SQL, (session_id, position, session_id, limit + 1))
            if not rows:
                raise ValueError(f"unknown node {position!r}")
            items = tuple(node_from_row(row) for row in rows[:limit])
            token = next_cursor(scope, rows[limit][0]) if len(rows) > limit else None
            return Page(items, token)

    def close(self) -> None:
        with self.lock:
            self.conn.close()


class AsyncSQLiteStore(AsyncStore):
    """Native aiosqlite implementation of the same tree contract."""

    def __init__(self, db_path: str | Path, *, clock: Clock = time.time) -> None:
        self.db_path = str(db_path)
        self.clock = clock
        self.lock = Lock()
        self.conn = None
        self.closed = False

    async def _connect(self) -> None:
        if self.closed:
            raise RuntimeError("store is closed")
        if self.conn is None:
            import aiosqlite

            if self.db_path != ":memory:":
                from contree_sdk.file_io import run_file_io

                await run_file_io(partial(Path(self.db_path).parent.mkdir, parents=True, exist_ok=True))
            connection = await aiosqlite.connect(self.db_path, isolation_level=None, timeout=30)
            try:
                await connection.execute("PRAGMA foreign_keys=ON")
                for statement in SCHEMA:
                    await connection.execute(statement)
            except BaseException:
                await shield(connection.close())
                raise
            self.conn = connection

    async def _rows(self, sql: str, args: tuple = ()) -> list[tuple]:
        if self.conn is None:
            raise RuntimeError("store is not connected")
        async with self.conn.execute(sql, args) as cursor:
            return [tuple(row) for row in await cursor.fetchall()]

    async def _write(self, sql: str, args: tuple = ()) -> None:
        if self.conn is None:
            raise RuntimeError("store is not connected")
        async with self.conn.execute(sql, args):
            pass

    @asynccontextmanager
    async def _transaction(self, *, write: bool = False) -> AsyncIterator[None]:
        async with self.lock:
            await self._connect()
            if self.conn is None:
                raise RuntimeError("store is not connected")
            try:
                await self.conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                yield
                await self.conn.commit()
            except BaseException:
                await shield(self.conn.rollback())
                raise

    async def _info(self, session_id: str) -> SessionInfo | None:
        rows = await self._rows(
            "SELECT id,kind,created,expires FROM tree_sessions WHERE id=? AND (expires IS NULL OR expires>?)",
            (session_id, self.clock()),
        )
        return SessionInfo(*rows[0]) if rows else None

    async def _require(self, session_id: str) -> SessionInfo:
        info = await self._info(session_id)
        if info is None:
            raise ValueError(f"unknown or expired session {session_id!r}")
        return info

    async def create_session(self, session_id: str, *, kind: str = "session", ttl: float | None = None) -> SessionInfo:
        if not isinstance(session_id, str) or not session_id or not isinstance(kind, str) or not kind:
            raise ValueError("session_id and kind must be nonempty strings")
        now = self.clock()
        expires = expiration(ttl, now)
        async with self._transaction(write=True):
            existing = await self._info(session_id)
            if existing is not None:
                if existing.kind != kind:
                    raise ValueError("session already exists with another kind")
                return existing
            await self._write("DELETE FROM tree_sessions WHERE id=?", (session_id,))
            await self._write("INSERT INTO tree_sessions VALUES (?,?,?,?)", (session_id, kind, now, expires))
            return SessionInfo(session_id, kind, now, expires)

    async def get_session(self, session_id: str) -> SessionInfo | None:
        async with self._transaction():
            return await self._info(session_id)

    async def set_session_ttl(self, session_id: str, ttl: float | None) -> SessionInfo:
        expires = expiration(ttl, self.clock())
        async with self._transaction(write=True):
            info = await self._require(session_id)
            await self._write("UPDATE tree_sessions SET expires=? WHERE id=?", (expires, session_id))
            return SessionInfo(info.session_id, info.kind, info.created_at, expires)

    async def delete_session(self, session_id: str) -> bool:
        async with self._transaction(write=True):
            found = bool(await self._rows("SELECT id FROM tree_sessions WHERE id=?", (session_id,)))
            await self._write("DELETE FROM tree_sessions WHERE id=?", (session_id,))
            return found

    async def list_sessions(
        self, *, kind: str | None = None, prefix: str = "", limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[SessionInfo]:
        scope = ("sessions", kind, prefix)
        after = cursor_position(cursor, scope, limit) or ""
        async with self._transaction():
            rows = await self._rows(*sessions_query(kind, prefix, after, self.clock(), limit))
            items = tuple(SessionInfo(*row) for row in rows[:limit])
            return Page(items, next_cursor(scope, items[-1].session_id) if len(rows) > limit else None)

    async def append(self, session_id: str, node: Node) -> None:
        payload = encode_data(node.data)
        async with self._transaction(write=True):
            await self._require(session_id)
            rows = await self._rows(
                "SELECT id,parent,kind,data FROM tree_nodes WHERE session_id=? AND id=?", (session_id, node.id)
            )
            if rows:
                if rows[0] != (node.id, node.parent_id, node.kind, payload):
                    raise NodeConflictError("node identity already has different contents")
                return
            if node.parent_id is None:
                if await self._rows("SELECT id FROM tree_nodes WHERE session_id=? AND parent IS NULL", (session_id,)):
                    raise NodeConflictError("tree already has a root")
            elif not await self._rows(
                "SELECT id FROM tree_nodes WHERE session_id=? AND id=?", (session_id, node.parent_id)
            ):
                raise ValueError("parent does not exist in this session")
            await self._write(
                "INSERT INTO tree_nodes VALUES (?,?,?,?,?)", (session_id, node.id, node.parent_id, node.kind, payload)
            )

    async def _node(self, session_id: str, node_id: str) -> Node:
        rows = await self._rows(
            "SELECT id,parent,kind,data FROM tree_nodes WHERE session_id=? AND id=?", (session_id, node_id)
        )
        if not rows:
            raise ValueError(f"unknown node {node_id!r}")
        return node_from_row(rows[0])

    async def get_node(self, session_id: str, node_id: str) -> Node:
        async with self._transaction():
            await self._require(session_id)
            return await self._node(session_id, node_id)

    async def get_nodes(self, session_id: str, node_ids: tuple[str, ...]) -> tuple[Node | None, ...]:
        validate_node_ids(node_ids)
        async with self._transaction():
            await self._require(session_id)
            found = {}
            for start in range(0, len(node_ids), SQL_BATCH_SIZE):
                rows = await self._rows(*batch_query(session_id, node_ids[start : start + SQL_BATCH_SIZE]))
                found.update((row[0], row) for row in rows)
            return tuple(node_from_row(found[node_id]) if node_id in found else None for node_id in node_ids)

    async def list_nodes(
        self, session_id: str, *, kind: str | None = None, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Node]:
        return await self._list_nodes(session_id, None, False, kind, limit, cursor)

    async def list_children(
        self,
        session_id: str,
        parent_id: str | None,
        *,
        kind: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[Node]:
        return await self._list_nodes(session_id, parent_id, True, kind, limit, cursor)

    async def _list_nodes(
        self, session_id: str, parent_id: str | None, children: bool, kind: str | None, limit: int, cursor: str | None
    ) -> Page[Node]:
        scope = ("nodes", session_id, parent_id, children, kind)
        after = cursor_position(cursor, scope, limit) or ""
        async with self._transaction():
            await self._require(session_id)
            if children and parent_id is not None:
                await self._node(session_id, parent_id)
            rows = await self._rows(*nodes_query(session_id, parent_id, children, kind, after, limit))
            items = tuple(node_from_row(row) for row in rows[:limit])
            return Page(items, next_cursor(scope, items[-1].id) if len(rows) > limit else None)

    async def list_history(
        self, session_id: str, from_node: str, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Node]:
        scope = ("history", session_id, from_node)
        async with self._transaction():
            position = cursor_position(cursor, scope, limit) or from_node
            await self._require(session_id)
            rows = await self._rows(HISTORY_SQL, (session_id, position, session_id, limit + 1))
            if not rows:
                raise ValueError(f"unknown node {position!r}")
            items = tuple(node_from_row(row) for row in rows[:limit])
            token = next_cursor(scope, rows[limit][0]) if len(rows) > limit else None
            return Page(items, token)

    async def close(self) -> None:
        async with self.lock:
            self.closed = True
            if self.conn is not None:
                await self.conn.close()
                self.conn = None
