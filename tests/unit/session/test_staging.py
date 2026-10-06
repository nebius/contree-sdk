"""Real session workflows retain staged uploads through failures and history changes."""

import inspect

import pytest
from contree_client.models import FileResponse, OperationStatus
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk import ContreeAsyncSession, ContreeSession
from contree_sdk.exceptions import FailedOperationError, SessionConflictError
from contree_sdk.files import UploadedFile, UploadFileSpec
from contree_sdk.store import AsyncMemoryStore, AsyncSQLiteStore, StagedFile, SyncMemoryStore, SyncSQLiteStore
from tests.unit.session.factories import mock_completion, operation_response, spawn_response


async def call(target, method, *args, **kwargs):
    result = getattr(target, method)(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


@pytest.fixture(params=["memory", "sqlite", "async-memory", "async-sqlite"])
async def staging_session(request, tmp_path):
    factories = {
        "memory": SyncMemoryStore,
        "sqlite": lambda: SyncSQLiteStore(tmp_path / "session.db"),
        "async-memory": AsyncMemoryStore,
        "async-sqlite": lambda: AsyncSQLiteStore(tmp_path / "session.db"),
    }
    store = factories[request.param]()
    session: ContreeSession | ContreeAsyncSession
    if isinstance(store, (AsyncMemoryStore, AsyncSQLiteStore)):
        async_client = ContreeAsyncClient()
        async_client.mock("resolve_image", "base")
        async_client.mock("ensure_file", FileResponse(uuid="upload", sha256="a" * 64, size=4))
        session = ContreeAsyncSession(async_client, image="base", session_id="session", store=store)
        await session.ensure_ready()
    else:
        client = ContreeClient()
        client.mock("resolve_image", "base")
        client.mock("ensure_file", FileResponse(uuid="upload", sha256="a" * 64, size=4))
        session = ContreeSession(client, image="base", session_id="session", store=store)
    yield session
    await call(session.store, "close")


def uploaded(uuid, *, mode=0o644):
    return UploadFileSpec(source=UploadedFile(uuid=uuid, sha256="a" * 64), uid=1234, gid=5678, mode=mode)


def complete(session, *, status=OperationStatus.SUCCESS):
    session.client.mock("spawn_instance", spawn_response())
    mock_completion(session.client, operation_response(status=status))


async def test_stage_resume_run_and_rollback_preserve_original_metadata(staging_session, tmp_path):
    session = staging_session
    staged = await call(session, "stage_files", {"/input": uploaded("original", mode=0o750)})
    expected = (StagedFile("/input", "original", 1234, 5678, 0o750),)
    assert session.image_uuid == "base"
    assert not session.client.calls_for("spawn_instance")
    if isinstance(session.store, (SyncSQLiteStore, AsyncSQLiteStore)):
        # Opening a second connection also checks that staging was committed.
        path = tmp_path / "session.db"
        await call(session.store, "close")
        session.store = type(session.store)(path)
    resumed = type(session)(session.client, session_id=session.session_id, store=session.store)
    assert await call(resumed, "pending_files") == expected
    complete(resumed)
    await call(resumed, "run", shell="cat /input", disposable=False)
    sent = resumed.client.calls_for("spawn_instance")[0].kwargs["files"]["/input"]
    assert (sent.uuid, sent.uid, sent.gid, sent.mode) == ("original", 1234, 5678, "0750")
    assert not resumed.client.calls_for("ensure_file")
    assert await call(resumed, "pending_files") == ()
    await call(resumed, "rollback")
    assert resumed.tip_id == staged.id
    assert await call(resumed, "pending_files") == expected


async def test_explicit_files_override_staging_without_consuming_disposable_branch(staging_session):
    session = staging_session
    await call(session, "stage_files", {"/input": uploaded("staged"), "/other": uploaded("other")})
    before = await call(session, "pending_files")
    complete(session)
    await call(session, "run", shell="cat /input", files={"/input": uploaded("explicit")})
    files = session.client.calls_for("spawn_instance")[0].kwargs["files"]
    assert files["/input"].uuid == "explicit"
    assert files["/other"].uuid == "other"
    assert await call(session, "pending_files") == before
    complete(session)
    await call(session, "run", shell="cat /input", files={"/input": uploaded("explicit")}, disposable=False)
    assert await call(session, "pending_files") == ()
    await call(session, "rollback")
    assert await call(session, "pending_files") == before


@pytest.mark.parametrize("status", [OperationStatus.FAILED, OperationStatus.CANCELLED])
async def test_failed_operation_retains_staging(staging_session, status):
    session = staging_session
    await call(session, "stage_files", {"/input": uploaded("staged")})
    before = await call(session.store, "read_session", session.session_id)
    complete(session, status=status)
    error = InterruptedError if status == OperationStatus.CANCELLED else FailedOperationError
    with pytest.raises(error):
        await call(session, "run", shell="cat /input", disposable=False)
    assert await call(session.store, "read_session", session.session_id) == before


async def test_upload_and_spawn_errors_do_not_change_staging(staging_session):
    session = staging_session
    await call(session, "stage_files", {"/input": uploaded("staged")})
    before = await call(session.store, "read_session", session.session_id)
    # Queue both outcomes before consuming the first one.
    session.client.mock("ensure_file", error=OSError("upload failed"))
    await call(session, "upload_file", UploadFileSpec(source=b"data", path="/not-staged"))
    with pytest.raises(OSError, match="upload failed"):
        await call(session, "stage_files", {"/input": b"replacement"})
    session.client.mock("spawn_instance", error=OSError("spawn failed"))
    with pytest.raises(OSError, match="spawn failed"):
        await call(session, "run", shell="cat /input", disposable=False)
    assert await call(session.store, "read_session", session.session_id) == before


async def test_file_record_override_does_not_disable_consumption(staging_session):
    session = staging_session
    await call(session, "stage_files", {"/input": uploaded("staged")})
    complete(session)
    operation = await call(session, "spawn", shell="cat /input", disposable=False)
    await call(operation, "wait")
    entry = await call(session, "commit_result", operation, files=())
    assert entry.files == ()
    assert entry.applied_files == ("/input",)
    assert await call(session, "pending_files") == ()


async def test_parallel_edit_causes_commit_conflict_and_can_be_saved_on_new_branch(staging_session):
    session = staging_session
    first = await call(session, "stage_files", {"/input": uploaded("staged")})
    complete(session)
    operation = await call(session, "spawn", shell="cat /input", disposable=False)
    await call(session, "stage_files", {"/input": uploaded("replacement")})
    await call(operation, "wait")
    with pytest.raises(SessionConflictError):
        await call(session, "commit_result", operation)
    assert (await call(session, "pending_files"))[0].uuid == "replacement"
    await call(session, "commit_result", operation, branch="completed")
    assert await call(session, "pending_files") == ()
    await call(session, "rollback")
    assert session.tip_id == first.id
    assert (await call(session, "pending_files"))[0].uuid == "staged"
    await call(session, "switch_branch", "main")
    assert (await call(session, "pending_files"))[0].uuid == "replacement"


async def test_stage_upload_is_not_repeated_when_the_source_changes(staging_session, tmp_path):
    session = staging_session
    path = tmp_path / "input.txt"
    path.write_bytes(b"old contents")
    await call(session, "stage_files", {"/input": path})
    path.unlink()
    complete(session)
    await call(session, "run", shell="cat /input", disposable=False)
    assert session.client.calls_for("ensure_file")[0].args[0].closed
    assert session.client.calls_for("ensure_file")[0].args[0].name == str(path)
    assert len(session.client.calls_for("ensure_file")) == 1
    assert session.client.calls_for("spawn_instance")[0].kwargs["files"]["/input"].uuid == "upload"


async def test_upload_keeps_its_original_branch_when_active_branch_changes(staging_session, monkeypatch):
    session = staging_session
    await call(session, "create_branch", "feature")
    await call(session, "switch_branch", "feature")
    await call(session, "stage_files", {"/feature": uploaded("feature")})
    await call(session, "switch_branch", "main")
    original = session.build_files
    if isinstance(session, ContreeAsyncSession):

        async def during_upload(files):
            await session.switch_branch("feature")
            return await original(files)

    else:

        def during_upload(files):
            session.switch_branch("feature")
            return original(files)

    monkeypatch.setattr(session, "build_files", during_upload)
    staged = await call(session, "stage_files", {"/main": uploaded("main")})
    assert (await call(session.store, "tip", "session", "main")).id == staged.id
    assert session.tip_id == (await call(session.store, "tip", "session", "feature")).id
    assert [item.path for item in await call(session, "pending_files")] == ["/feature"]


async def test_upload_captures_expected_tip_before_other_edits(staging_session, monkeypatch):
    session = staging_session
    original = session.build_files
    replacement = StagedFile("/input", "newer")
    if isinstance(session, ContreeAsyncSession):

        async def during_upload(files):
            entry = await session.store.stage_files("session", [replacement])
            await session.refresh_from_entry(entry)
            return await original(files)

    else:

        def during_upload(files):
            entry = session.store.stage_files("session", [replacement])
            session.refresh_from_entry(entry)
            return original(files)

    monkeypatch.setattr(session, "build_files", during_upload)
    with pytest.raises(SessionConflictError):
        await call(session, "stage_files", {"/input": uploaded("stale")})
    assert await call(session, "pending_files") == (replacement,)
