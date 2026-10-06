from pathlib import Path

import pytest

from contree_sdk.cache import SyncSQLiteCache


def test_cache_survives_reopen(tmp_path: Path):
    db_path = tmp_path / "cache.db"

    first = SyncSQLiteCache(db_path)
    first.set("key1", {"uuid": "abc"})
    first.close()

    reopened = SyncSQLiteCache(db_path)
    assert reopened.get("key1") == {"uuid": "abc"}
    reopened.close()


def test_second_connection_sees_writes_from_first(tmp_path: Path):
    db_path = tmp_path / "cache.db"

    writer = SyncSQLiteCache(db_path)
    reader = SyncSQLiteCache(db_path)

    writer.set("key1", "value1")
    assert reader.get("key1") == "value1"

    writer.set("key1", "value2")
    assert reader.get("key1") == "value2"

    writer.close()
    reader.close()


def test_transaction_rolls_back_on_error_so_second_connection_can_still_write(tmp_path: Path):
    # any exception mid-write must not leave the connection's transaction open,
    # else a second connection's write hangs/fails with "database is locked"
    db_path = tmp_path / "cache.db"

    writer = SyncSQLiteCache(db_path)

    def failing_write() -> None:
        with writer.transaction():
            writer.conn.execute(
                "INSERT INTO cache_v1 (namespace, key, value) VALUES (?, ?, ?)",
                ("default", "key1", '"value1"'),
            )
            raise RuntimeError("simulated failure mid-write")

    with pytest.raises(RuntimeError, match="simulated failure"):
        failing_write()

    reader = SyncSQLiteCache(db_path)
    reader.conn.execute("PRAGMA busy_timeout=200")
    reader.set("key2", "value2")

    writer.close()
    reader.close()
