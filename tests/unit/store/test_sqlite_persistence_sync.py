from pathlib import Path

import pytest

from contree_sdk.store import SyncSQLiteStore


def test_history_survives_reopen(tmp_path: Path):
    db_path = tmp_path / "sessions.db"

    first = SyncSQLiteStore(db_path)
    root = first.append("s1", image_uuid="img-0", parent_id=None)
    first.append("s1", image_uuid="img-1", parent_id=root.id, title="echo hi")
    first.close()

    reopened = SyncSQLiteStore(db_path)
    tip = reopened.tip("s1")
    assert tip is not None
    assert tip.image_uuid == "img-1"
    reopened.close()


def test_second_connection_sees_writes_from_first(tmp_path: Path):
    db_path = tmp_path / "sessions.db"

    writer = SyncSQLiteStore(db_path)
    reader = SyncSQLiteStore(db_path)

    root = writer.append("s1", image_uuid="img-0", parent_id=None)
    assert reader.tip("s1") == root

    child = writer.append("s1", image_uuid="img-1", parent_id=root.id)
    assert reader.tip("s1") == child

    writer.close()
    reader.close()


def test_failed_delete_branch_rolls_back_so_second_connection_can_still_write(tmp_path: Path):
    # delete_branch's DELETE opens an implicit write transaction, then raises on a
    # 0-row match; without a rollback on that error path the transaction stays open
    # and a second connection's write hangs/fails with "database is locked"
    db_path = tmp_path / "sessions.db"

    writer1 = SyncSQLiteStore(db_path)
    root = writer1.append("s1", image_uuid="img-0", parent_id=None)

    with pytest.raises(ValueError, match="does not exist"):
        writer1.delete_branch("s1", "missing")

    writer2 = SyncSQLiteStore(db_path)
    writer2.conn.execute("PRAGMA busy_timeout=200")
    writer2.append("s1", image_uuid="img-1", parent_id=root.id)

    writer1.close()
    writer2.close()
