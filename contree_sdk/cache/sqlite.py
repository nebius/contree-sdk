from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from asyncio import Lock
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import Any

from contree_sdk.cache.base import AsyncCache, SyncCache
from contree_sdk.cache.models import CacheEntry, Clock, expiration


try:
    import aiosqlite

    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False


DB_TIMEOUT = float(os.getenv("CONTREE_DB_TIMEOUT", "30"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache_v2 (
    namespace TEXT NOT NULL,
    key       TEXT NOT NULL,
    value     TEXT NOT NULL,
    expires_at REAL,
    PRIMARY KEY (namespace, key)
);
"""


class SyncSQLiteCache(SyncCache):
    """SQLite-backed Cache: one file, JSON-encoded values, shared across processes.

    WAL journal mode + a busy timeout make the file safe to share across
    *processes*. `check_same_thread=False` plus a `threading.RLock` make one
    instance safe to share across *threads* within this process too.

    No in-place schema migrations: the table is named `cache_v2`. The previous
    disposable cache_v1 values are not imported. Permanent source records
    introduced in cache_v2 must be preserved by future schema upgrades.
    """

    def __init__(self, db_path: str | Path, *, clock: Clock = time.time) -> None:
        self.clock = clock
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

    def get_entry(self, key: str, *, namespace: str = "default") -> CacheEntry | None:
        with self.rlock:
            row = self.conn.execute(
                "SELECT value, expires_at FROM cache_v2 WHERE namespace = ? AND key = ? "
                "AND (expires_at IS NULL OR expires_at > ?)",
                (namespace, key, self.clock()),
            ).fetchone()
        return None if row is None else CacheEntry(key, json.loads(row["value"]), row["expires_at"])

    def set(self, key: str, value: Any, *, namespace: str = "default", ttl: float | None = None) -> None:
        encoded = json.dumps(value, allow_nan=False)
        expires_at = expiration(ttl, self.clock())
        with self.rlock, self.transaction():
            self.conn.execute(
                "INSERT INTO cache_v2 (namespace, key, value, expires_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(namespace, key) DO UPDATE SET value = excluded.value, expires_at = excluded.expires_at",
                (namespace, key, encoded, expires_at),
            )
            self.conn.commit()

    def entries(self, *, namespace: str = "default", prefix: str = "") -> tuple[CacheEntry, ...]:
        with self.rlock:
            rows = self.conn.execute(
                "SELECT key, value, expires_at FROM cache_v2 WHERE namespace = ? "
                "AND substr(CAST(key AS BLOB), 1, length(CAST(? AS BLOB))) = CAST(? AS BLOB) "
                "AND (expires_at IS NULL OR expires_at > ?) ORDER BY key",
                (namespace, prefix, prefix, self.clock()),
            ).fetchall()
        return tuple(CacheEntry(row["key"], json.loads(row["value"]), row["expires_at"]) for row in rows)

    def delete(self, key: str, *, namespace: str = "default") -> bool:
        with self.rlock, self.transaction():
            cursor = self.conn.execute("DELETE FROM cache_v2 WHERE namespace = ? AND key = ?", (namespace, key))
            self.conn.commit()
            return cursor.rowcount > 0

    def invalidate(self, *, namespace: str = "default", prefix: str = "") -> int:
        with self.rlock, self.transaction():
            cursor = self.conn.execute(
                "DELETE FROM cache_v2 WHERE namespace = ? "
                "AND substr(CAST(key AS BLOB), 1, length(CAST(? AS BLOB))) = CAST(? AS BLOB)",
                (namespace, prefix, prefix),
            )
            self.conn.commit()
            return cursor.rowcount


class AsyncSQLiteCache(AsyncCache):
    """SQLite-backed Cache using aiosqlite: one file, JSON-encoded values.

    The connection opens lazily on first use, since `aiosqlite.connect()` is
    itself a coroutine and can't run in `__init__`. Requires the
    `contree-sdk[async]` extra.

    No in-place schema migrations: the table is named `cache_v2`. The previous
    disposable cache_v1 values are not imported. Permanent source records
    introduced in cache_v2 must be preserved by future schema upgrades.
    """

    def __init__(self, db_path: str | Path, *, clock: Clock = time.time) -> None:
        self.clock = clock
        if not AIOSQLITE_AVAILABLE:
            raise ImportError('AsyncSQLiteCache requires aiosqlite; install it via `pip install "contree-sdk[async]"`')
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

    async def get_entry(self, key: str, *, namespace: str = "default") -> CacheEntry | None:
        conn = await self.ensure_connection()
        async with self.lock:
            cursor = await conn.execute(
                "SELECT value, expires_at FROM cache_v2 WHERE namespace = ? AND key = ? "
                "AND (expires_at IS NULL OR expires_at > ?)",
                (namespace, key, self.clock()),
            )
            row = await cursor.fetchone()
        return None if row is None else CacheEntry(key, json.loads(row["value"]), row["expires_at"])

    async def set(self, key: str, value: Any, *, namespace: str = "default", ttl: float | None = None) -> None:
        encoded = json.dumps(value, allow_nan=False)
        expires_at = expiration(ttl, self.clock())
        conn = await self.ensure_connection()
        async with self.lock, self.transaction():
            await conn.execute(
                "INSERT INTO cache_v2 (namespace, key, value, expires_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(namespace, key) DO UPDATE SET value = excluded.value, expires_at = excluded.expires_at",
                (namespace, key, encoded, expires_at),
            )
            await conn.commit()

    async def entries(self, *, namespace: str = "default", prefix: str = "") -> tuple[CacheEntry, ...]:
        conn = await self.ensure_connection()
        async with self.lock:
            cursor = await conn.execute(
                "SELECT key, value, expires_at FROM cache_v2 WHERE namespace = ? "
                "AND substr(CAST(key AS BLOB), 1, length(CAST(? AS BLOB))) = CAST(? AS BLOB) "
                "AND (expires_at IS NULL OR expires_at > ?) ORDER BY key",
                (namespace, prefix, prefix, self.clock()),
            )
            rows = await cursor.fetchall()
        return tuple(CacheEntry(row["key"], json.loads(row["value"]), row["expires_at"]) for row in rows)

    async def delete(self, key: str, *, namespace: str = "default") -> bool:
        conn = await self.ensure_connection()
        async with self.lock, self.transaction():
            cursor = await conn.execute("DELETE FROM cache_v2 WHERE namespace = ? AND key = ?", (namespace, key))
            await conn.commit()
            return cursor.rowcount > 0

    async def invalidate(self, *, namespace: str = "default", prefix: str = "") -> int:
        conn = await self.ensure_connection()
        async with self.lock, self.transaction():
            cursor = await conn.execute(
                "DELETE FROM cache_v2 WHERE namespace = ? "
                "AND substr(CAST(key AS BLOB), 1, length(CAST(? AS BLOB))) = CAST(? AS BLOB)",
                (namespace, prefix, prefix),
            )
            await conn.commit()
            return cursor.rowcount
