from pathlib import Path

from contree_sdk.store import AsyncSQLiteStore


async def test_history_survives_reopen(tmp_path: Path):
    db_path = tmp_path / "sessions.db"

    first = AsyncSQLiteStore(db_path)
    root = await first.append("s1", image_uuid="img-0", parent_id=None)
    await first.append("s1", image_uuid="img-1", parent_id=root.id, title="echo hi")
    await first.close()

    reopened = AsyncSQLiteStore(db_path)
    tip = await reopened.tip("s1")
    assert tip is not None
    assert tip.image_uuid == "img-1"
    await reopened.close()


async def test_second_connection_sees_writes_from_first(tmp_path: Path):
    db_path = tmp_path / "sessions.db"

    writer = AsyncSQLiteStore(db_path)
    reader = AsyncSQLiteStore(db_path)

    root = await writer.append("s1", image_uuid="img-0", parent_id=None)
    assert await reader.tip("s1") == root

    child = await writer.append("s1", image_uuid="img-1", parent_id=root.id)
    assert await reader.tip("s1") == child

    await writer.close()
    await reader.close()
