from __future__ import annotations

import json
import os
import sqlite3
import threading
from asyncio import Lock
from pathlib import Path
from typing import Any

from contree_sdk.cache.base import AsyncCache, SyncCache


try:
    import aiosqlite

    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False


DB_TIMEOUT = float(os.getenv("CONTREE_DB_TIMEOUT", "30"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class SyncSQLiteCache(SyncCache):
    """SQLite-backed Cache: one file, JSON-encoded values, shared across processes.

    WAL journal mode + a busy timeout make the file safe to share across
    *processes*. `check_same_thread=False` plus a `threading.RLock` make one
    instance safe to share across *threads* within this process too.
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

    def get(self, key: str) -> Any | None:
        with self.rlock:
            row = self.conn.execute("SELECT value FROM cache WHERE key = ?", (key,)).fetchone()
        return None if row is None else json.loads(row["value"])

    def set(self, key: str, value: Any) -> None:
        """Store `value` as JSON; it must be JSON-serializable."""
        with self.rlock:
            self.conn.execute(
                """
                INSERT INTO cache (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, json.dumps(value)),
            )
            self.conn.commit()


class AsyncSQLiteCache(AsyncCache):
    """SQLite-backed Cache using aiosqlite: one file, JSON-encoded values.

    The connection opens lazily on first use, since `aiosqlite.connect()` is
    itself a coroutine and can't run in `__init__`. Requires the
    `contree-sdk[async]` extra.
    """

    def __init__(self, db_path: str | Path) -> None:
        if not AIOSQLITE_AVAILABLE:
            raise ImportError('AsyncSQLiteCache requires aiosqlite; install it via `pip install "contree-sdk[async]"`')
        self.db_path = Path(db_path)
        self.conn: aiosqlite.Connection | None = None
        self.connect_lock = Lock()

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

    async def get(self, key: str) -> Any | None:
        conn = await self.ensure_connection()
        cursor = await conn.execute("SELECT value FROM cache WHERE key = ?", (key,))
        row = await cursor.fetchone()
        return None if row is None else json.loads(row["value"])

    async def set(self, key: str, value: Any) -> None:
        """Store `value` as JSON; it must be JSON-serializable."""
        conn = await self.ensure_connection()
        await conn.execute(
            """
            INSERT INTO cache (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, json.dumps(value)),
        )
        await conn.commit()
