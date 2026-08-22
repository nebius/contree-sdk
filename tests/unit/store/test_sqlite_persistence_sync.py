from pathlib import Path

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
