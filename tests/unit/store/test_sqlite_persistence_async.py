from pathlib import Path

import pytest

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


async def test_failed_delete_branch_rolls_back_so_second_connection_can_still_write(tmp_path: Path):
    # delete_branch's DELETE opens an implicit write transaction, then raises on a
    # 0-row match; without a rollback on that error path the transaction stays open
    # and a second connection's write hangs/fails with "database is locked"
    db_path = tmp_path / "sessions.db"

    writer1 = AsyncSQLiteStore(db_path)
    root = await writer1.append("s1", image_uuid="img-0", parent_id=None)

    with pytest.raises(ValueError, match="does not exist"):
        await writer1.delete_branch("s1", "missing")

    writer2 = AsyncSQLiteStore(db_path)
    conn2 = await writer2.ensure_connection()
    await conn2.execute("PRAGMA busy_timeout=200")
    await writer2.append("s1", image_uuid="img-1", parent_id=root.id)

    await writer1.close()
    await writer2.close()
