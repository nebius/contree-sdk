"""Staging is part of the history DAG, rather than mutable session metadata."""

import sqlite3

import pytest
from contree_client.models import FileSpec

from contree_sdk.exceptions import SessionConflictError
from contree_sdk.store import AsyncSQLiteStore, StagedFile, SyncSQLiteStore
from tests.unit.store.test_queries import call


async def seed(store):
    return await call(store, "append", "session", image_uuid="base", parent_id=None)


async def test_stage_versions_follow_ancestry_and_branch_isolation(store_case):
    root = await seed(store_case)
    original = StagedFile("/work/data", "original", 1001, 1002, 0o750)
    other = StagedFile("/other", "other")
    first = await call(store_case, "stage_files", "session", [original, other])
    assert first.kind == "stage"
    assert first.image_uuid == root.image_uuid
    assert first.parent_id == root.id
    assert await call(store_case, "pending_files", "session") == (other, original)
    await call(store_case, "create_branch", "session", "feature")
    replacement = StagedFile("/work/data", "replacement", 7, 8, 0o600)
    second = await call(store_case, "stage_files", "session", [replacement], branch="feature")
    assert await call(store_case, "tip", "session") == first
    assert await call(store_case, "pending_files", "session", branch="feature") == (other, replacement)
    assert await call(store_case, "pending_files", "session") == (other, original)
    committed = await call(
        store_case,
        "append",
        "session",
        image_uuid="result",
        parent_id=second.id,
        branch="feature",
        applied_files=("/work/data",),
        expected_tip=second.id,
    )
    assert await call(store_case, "pending_files", "session", branch="feature") == (other,)
    await call(store_case, "switch_branch", "session", "feature")
    await call(store_case, "rollback", "session")
    assert await call(store_case, "pending_files", "session") == (other, replacement)
    await call(store_case, "rollback", "session")
    assert await call(store_case, "pending_files", "session") == (other, original)
    assert await call(store_case, "pending_files", "session", history_id=root.id) == ()
    snapshot = await call(store_case, "read_session", "session")
    assert snapshot.pending_files(history_id=committed.id) == (other,)
    assert snapshot.pending_files(history_id=second.id) == (other, replacement)
    assert snapshot.resolve(history_id=second.id).attachments == (replacement,)


async def test_informational_files_do_not_consume_staging(store_case):
    await seed(store_case)
    item = StagedFile("/input", "upload")
    staged = await call(store_case, "stage_files", "session", [item])
    await call(store_case, "append", "session", image_uuid="base", parent_id=staged.id, files=("/input",))
    assert await call(store_case, "pending_files", "session") == (item,)


@pytest.mark.parametrize("batch", [[], [StagedFile("/data", "a"), StagedFile("/./data", "b")]])
async def test_invalid_batch_is_atomic(store_case, batch):
    await seed(store_case)
    before = await call(store_case, "read_session", "session")
    with pytest.raises(ValueError):
        await call(store_case, "stage_files", "session", batch)
    assert await call(store_case, "read_session", "session") == before


async def test_stale_writes_cannot_consume_or_replace_pending_files(store_case):
    root = await seed(store_case)
    item = StagedFile("/input", "upload")
    staged = await call(store_case, "stage_files", "session", [item])
    before = await call(store_case, "read_session", "session")
    with pytest.raises(SessionConflictError):
        await call(store_case, "stage_files", "session", [StagedFile("/input", "new")], expected_tip=root.id)
    with pytest.raises(SessionConflictError):
        await call(
            store_case,
            "append",
            "session",
            image_uuid="result",
            parent_id=root.id,
            applied_files=("/input",),
            expected_tip=root.id,
        )
    assert await call(store_case, "read_session", "session") == before
    assert await call(store_case, "pending_files", "session", history_id=staged.id) == (item,)


async def test_staging_checks_session_membership_and_requires_existing_branch(store_case):
    await seed(store_case)
    foreign = await call(store_case, "append", "other", image_uuid="other", parent_id=None)
    item = StagedFile("/input", "upload")
    with pytest.raises(ValueError):
        await call(store_case, "pending_files", "session", history_id=foreign.id)
    for session, branch in [("session", "missing"), ("missing", None)]:
        with pytest.raises(ValueError):
            await call(store_case, "stage_files", session, [item], branch=branch)
    assert await call(store_case, "list_sessions") == ["other", "session"]


async def test_deleting_session_does_not_leave_staging_for_reused_name(store_case):
    await seed(store_case)
    await call(store_case, "stage_files", "session", [StagedFile("/input", "upload")])
    await call(store_case, "delete_session", "session")
    await seed(store_case)
    assert await call(store_case, "pending_files", "session") == ()


@pytest.mark.parametrize(
    ("writer_factory", "reader_factory"),
    [
        (SyncSQLiteStore, AsyncSQLiteStore),
        (AsyncSQLiteStore, SyncSQLiteStore),
    ],
)
async def test_staging_survives_reopen_between_sync_and_async(tmp_path, writer_factory, reader_factory):
    path = tmp_path / "session.db"
    writer = writer_factory(path)
    await seed(writer)
    item = StagedFile("/input", "upload", None, 1234, None)
    staged = await call(writer, "stage_files", "session", [item])
    await call(writer, "close")
    reader = reader_factory(path)
    try:
        assert await call(reader, "get_entry", "session", staged.id) == staged
        assert await call(reader, "pending_files", "session") == (item,)
        await call(reader, "append", "session", image_uuid="result", parent_id=staged.id, applied_files=("/input",))
    finally:
        await call(reader, "close")
    writer = writer_factory(path)
    try:
        assert await call(writer, "pending_files", "session") == ()
        await call(writer, "rollback", "session")
        assert await call(writer, "pending_files", "session") == (item,)
    finally:
        await call(writer, "close")


@pytest.mark.parametrize("factory", [SyncSQLiteStore, AsyncSQLiteStore])
@pytest.mark.parametrize(
    ("table", "kwargs"),
    [
        ("attachments", {"attachments": (StagedFile("/input", "replacement"),)}),
        ("applied_files", {"applied_files": ("/input",)}),
    ],
)
async def test_sql_failure_rolls_back_history_and_staging(tmp_path, factory, table, kwargs):
    path = tmp_path / "session.db"
    store = factory(path)
    try:
        await seed(store)
        staged = await call(store, "stage_files", "session", [StagedFile("/input", "upload")])
        before = await call(store, "read_session", "session")
        with sqlite3.connect(path) as fault:
            fault.execute(
                f"CREATE TRIGGER fail_insert BEFORE INSERT ON session_history_{table}_v1 "
                "BEGIN SELECT RAISE(ABORT, 'staging failure'); END;"
            )
        with pytest.raises(sqlite3.IntegrityError, match="staging failure"):
            await call(store, "append", "session", image_uuid="result", parent_id=staged.id, **kwargs)
        assert await call(store, "read_session", "session") == before
    finally:
        await call(store, "close")


def test_attachment_copies_transport_fields_and_normalizes_octal_mode():
    spec = FileSpec(uuid="upload", uid=123, mode="0751")
    item = StagedFile.from_spec("/work/./input", spec)
    spec.uuid = "changed"
    assert item == StagedFile("/work/input", "upload", 123, None, 0o751)
    restored = item.as_spec()
    assert restored.uuid == "upload"
    assert restored.mode == "0751"
    assert restored.gid is Ellipsis
    for path, spec in [("", FileSpec(uuid="upload")), ("/input", FileSpec()), ("/input", FileSpec(uuid=""))]:
        with pytest.raises(ValueError):
            StagedFile.from_spec(path, spec)
