from pathlib import Path

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
