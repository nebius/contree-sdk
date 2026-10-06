import sqlite3
from pathlib import Path

import pytest

from contree_sdk.cache import AsyncSQLiteCache


async def test_cache_survives_reopen(tmp_path: Path):
    db_path = tmp_path / "cache.db"

    first = AsyncSQLiteCache(db_path)
    await first.set("key1", {"uuid": "abc"})
    await first.close()

    reopened = AsyncSQLiteCache(db_path)
    assert await reopened.get("key1") == {"uuid": "abc"}
    await reopened.close()


async def test_second_connection_sees_writes_from_first(tmp_path: Path):
    db_path = tmp_path / "cache.db"

    writer = AsyncSQLiteCache(db_path)
    reader = AsyncSQLiteCache(db_path)

    await writer.set("key1", "value1")
    assert await reader.get("key1") == "value1"

    await writer.set("key1", "value2")
    assert await reader.get("key1") == "value2"

    await writer.close()
    await reader.close()


async def test_failed_write_rolls_back_so_second_connection_can_still_write(tmp_path: Path):
    # a commit failure mid-write must not leave the connection's transaction open,
    # else a second connection's write hangs/fails with "database is locked"
    db_path = tmp_path / "cache.db"

    writer = AsyncSQLiteCache(db_path)
    conn = await writer.ensure_connection()

    async def failing_commit() -> None:
        raise sqlite3.OperationalError("simulated commit failure")

    conn.commit = failing_commit  # ty: ignore[invalid-assignment]
    with pytest.raises(sqlite3.OperationalError):
        await writer.set("key1", "value1")

    reader = AsyncSQLiteCache(db_path)
    reader_conn = await reader.ensure_connection()
    await reader_conn.execute("PRAGMA busy_timeout=200")
    await reader.set("key2", "value2")

    await writer.close()
    await reader.close()
