from pathlib import Path

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
