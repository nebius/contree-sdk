import asyncio

import pytest
from contree_client.models import FileResponse, OperationStatus
from contree_client.testing import ContreeAsyncClient

from contree_sdk.exceptions import FailedOperationError
from contree_sdk.session import AsyncOperation, ContreeAsyncSession
from contree_sdk.store import AsyncMemoryStore
from tests.unit.session.factories import mock_completion, operation_response, spawn_response


@pytest.fixture
def client() -> ContreeAsyncClient:
    client = ContreeAsyncClient()
    client.mock("resolve_image", "img-uuid-0")
    return client


async def test_construct_resolves_image_and_seeds_history(client: ContreeAsyncClient):
    store = AsyncMemoryStore()
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=store)

    await session.ensure_ready()
    assert session.image_uuid == "img-uuid-0"
    entries, _ = await session.history()
    assert [entry.kind for entry in entries] == ["init"]


def test_construct_requires_image_or_session_id(client: ContreeAsyncClient):
    with pytest.raises(ValueError):
        ContreeAsyncSession(client)


async def test_concurrent_ensure_ready_creates_only_one_init_entry(client: ContreeAsyncClient):
    # two concurrent first calls (e.g. two concurrent .run()s on a fresh session)
    # must not both observe ready=False and each append their own "init" root
    store = AsyncMemoryStore()
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=store)

    async def slow_resolve_image(image: str) -> str:
        await asyncio.sleep(0)
        return "img-uuid-0"

    client.resolve_image = slow_resolve_image  # ty: ignore[invalid-assignment]

    await asyncio.gather(session.ensure_ready(), session.ensure_ready())

    entries, _ = await session.history()
    assert [entry.kind for entry in entries] == ["init"]


async def test_construct_resumes_from_existing_session(client: ContreeAsyncClient):
    store = AsyncMemoryStore()
    first = ContreeAsyncSession(client, image="tag:python:3.11", store=store, session_id="my-session")
    await first.ensure_ready()

    resumed = ContreeAsyncSession(client, store=store, session_id="my-session")
    await resumed.ensure_ready()
    assert resumed.image_uuid == first.image_uuid
    assert resumed.tip_id == first.tip_id


async def test_run_disposable_does_not_advance_history(client: ContreeAsyncClient):
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response())
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=AsyncMemoryStore())

    result = await session.run(shell="echo hi", disposable=True)

    assert result.stdout.as_text() == "hi\n"
    assert result.state.exit_code == 0
    entries, _ = await session.history()
    assert [entry.kind for entry in entries] == ["init"]
    assert session.image_uuid == "img-uuid-0"


async def test_run_default_advances_history_and_pointer(client: ContreeAsyncClient):
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response(result_image_uuid="img-uuid-1", exit_code=0))
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=AsyncMemoryStore())

    result = await session.run(shell="echo hi")

    assert result.state.exit_code == 0
    assert session.image_uuid == "img-uuid-1"
    entries, _ = await session.history()
    assert [entry.kind for entry in entries] == ["init", "run"]
    assert entries[-1].exit_code == 0
    assert entries[-1].operation_uuid == "op-1"


async def test_run_nonzero_exit_code_is_not_an_error(client: ContreeAsyncClient):
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response(exit_code=1, stdout="", stderr="boom"))
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=AsyncMemoryStore())

    result = await session.run(shell="false")

    assert result.state.exit_code == 1
    assert result.stderr.as_text() == "boom"


async def test_run_operation_failure_without_result_raises(client: ContreeAsyncClient):
    client.mock("spawn_instance", spawn_response())
    mock_completion(
        client,
        operation_response(status=OperationStatus.FAILED, error="vm could not start", with_result=False),
    )
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=AsyncMemoryStore())

    with pytest.raises(FailedOperationError):
        await session.run(shell="echo hi")


async def test_run_requires_command_or_shell(client: ContreeAsyncClient):
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=AsyncMemoryStore())
    with pytest.raises(ValueError):
        await session.run()


async def test_run_rejects_both_command_and_shell(client: ContreeAsyncClient):
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=AsyncMemoryStore())
    with pytest.raises(ValueError):
        await session.run(command="echo hi", shell="echo hi")


async def test_branch_and_rollback_update_live_pointer(client: ContreeAsyncClient):
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response(result_image_uuid="img-uuid-1"))
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=AsyncMemoryStore())
    await session.run(shell="echo hi", disposable=False)

    await session.create_branch("feature")
    await session.switch_branch("feature")
    assert dict(await session.list_branches()) == {"main": False, "feature": True}
    assert session.image_uuid == "img-uuid-1"

    await session.rollback()
    assert session.image_uuid == "img-uuid-0"


@pytest.mark.parametrize("action", ["commit", "detached_commit", "wait_operation", "stage_files"])
@pytest.mark.parametrize("navigation", ["navigate", "switch_branch"])
async def test_navigation_during_refresh_keeps_selection_consistent(client, monkeypatch, action, navigation):
    client.mock("spawn_instance", spawn_response())
    client.mock("ensure_file", FileResponse(uuid="file-uuid-1", sha256="deadbeef", size=4))
    mock_completion(client, operation_response(result_image_uuid="completed-image"))
    store = AsyncMemoryStore()
    session = ContreeAsyncSession(client, image="base", store=store, cwd="/selected", env={"STATE": "selected"})
    await session.ensure_ready()
    selected_id = session.tip_id
    await session.create_branch("selected")
    await session.set_cwd("/source")
    await session.set_env({"STATE": "source"})
    source_id = session.tip_id
    operation = await session.spawn("command")
    if action in {"detached_commit", "wait_operation"}:
        await session.detach(operation)
    if action in {"commit", "detached_commit"}:
        await operation.wait()

    navigation_task: asyncio.Task[None] | None = None
    refresh_from_entry = session.refresh_from_entry
    get_node = store.get_node

    async def refresh_with_navigation(entry):
        nonlocal navigation_task
        if navigation_task is None:
            target = selected_id if navigation == "navigate" else "selected"
            navigation_task = asyncio.create_task(getattr(session, navigation)(target))
        await refresh_from_entry(entry)

    async def read_after_navigation(session_id, node_id):
        # A Store read after the position guard lets the queued navigation complete first.
        if navigation_task is not None and asyncio.current_task() is not navigation_task:
            await navigation_task
        return await get_node(session_id, node_id)

    monkeypatch.setattr(session, "refresh_from_entry", refresh_with_navigation)
    monkeypatch.setattr(store, "get_node", read_after_navigation)

    if action == "stage_files":
        await session.stage_files({"/app.txt": b"data"})
    elif action == "wait_operation":
        await session.wait_operation(operation.uuid)
    else:
        await session.commit_result(operation)
    assert navigation_task is not None
    await navigation_task

    assert session.tip_id == selected_id
    assert session.image_uuid == "img-uuid-0"
    assert session.cwd == "/selected"
    assert session.env == {"STATE": "selected"}
    selected_branch = "main" if navigation == "navigate" else "selected"
    entries, branches = await session.history()
    assert selected_branch in branches[selected_id]
    saved = [entry for entry in entries if entry.parent_id == source_id]
    assert len(saved) == 1
    assert saved[0].cwd == "/source"
    assert saved[0].env == {"STATE": "source"}
    await store.close()


async def test_set_cwd_and_set_env_persist_through_store(client: ContreeAsyncClient):
    store = AsyncMemoryStore()
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=store, session_id="s1")

    await session.set_cwd("/app")
    await session.set_env({"FOO": "1", "BAR": "2"})

    assert session.cwd == "/app"
    assert session.env == {"FOO": "1", "BAR": "2"}
    metadata = (await store.get_node("s1", session.tip_id)).data
    assert metadata["cwd"] == "/app"
    assert metadata["env"] == {"FOO": "1", "BAR": "2"}

    await session.set_env({"BAR": None})
    assert session.env == {"FOO": "1"}
    assert (await store.get_node("s1", session.tip_id)).data["env"] == {"FOO": "1"}

    resumed = ContreeAsyncSession(client, image="tag:python:3.11", store=store, session_id="s1")
    await resumed.ensure_ready()
    assert resumed.cwd == "/app"
    assert resumed.env == {"FOO": "1"}


async def test_run_non_disposable_with_files_records_them_on_the_entry(client: ContreeAsyncClient):
    client.mock("ensure_file", FileResponse(uuid="file-uuid-1", sha256="deadbeef", size=4))
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response(result_image_uuid="img-uuid-1", exit_code=0))
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=AsyncMemoryStore())

    await session.run(shell="echo hi", disposable=False, files={"/app.txt": b"data"})

    entries, _ = await session.history()
    assert entries[-1].files == ("/app.txt",)


async def test_run_as_async_context_manager_yields_operation_without_waiting(client: ContreeAsyncClient):
    client.mock("spawn_instance", spawn_response())
    client.mock("follow_operation_events", [])
    client.mock("operation_subprocess_kill", None)
    client.mock("cancel_operation", None)
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=AsyncMemoryStore())

    async with session.run(shell="sleep 600", disposable=True) as operation:
        assert isinstance(operation, AsyncOperation)
        assert operation.uuid == "op-1"

    # Explicit disposable run: entering/exiting the context manager alone must not commit
    entries, _ = await session.history()
    assert [entry.kind for entry in entries] == ["init"]


async def test_run_as_async_context_manager_commits_on_clean_success_exit(client: ContreeAsyncClient):
    client.mock("spawn_instance", spawn_response())
    client.mock("follow_operation_events", [])
    client.mock("operation_subprocess_kill", None)
    client.mock("cancel_operation", None)
    client.mock("get_operation_status", operation_response(result_image_uuid="img-uuid-1", exit_code=0))
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=AsyncMemoryStore())

    async with session.run(shell="echo hi"):
        pass

    entries, _ = await session.history()
    assert [entry.kind for entry in entries] == ["init", "run"]
    assert entries[-1].image_uuid == "img-uuid-1"
    assert session.image_uuid == "img-uuid-1"


async def test_cancelled_operation_with_partial_result_is_not_committed(client):
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response(status=OperationStatus.CANCELLED))
    session = ContreeAsyncSession(client, image="base")
    with pytest.raises(InterruptedError):
        await session.run("sleep", disposable=False)
    entries, _ = await session.history()
    assert len(entries) == 1


async def test_stale_operation_does_not_rewrite_history(client):

    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response())
    session = ContreeAsyncSession(client, image="base")
    first = await session.spawn("first", disposable=False)
    second = await session.spawn("second", disposable=False)
    await first.wait()
    await second.wait()
    committed = await session.commit_result(first)
    assert committed is not None
    sibling = await session.commit_result(second)
    assert sibling is not None
    assert sibling.parent_id == committed.parent_id
    assert sibling.id != committed.id
    entries, _ = await session.history()
    assert len(entries) == 3
    assert session.tip_id == committed.id


async def test_commit_after_branch_switch_preserves_active_branch(client):
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response())
    session = ContreeAsyncSession(client, image="base")
    await session.create_branch("other")
    operation = await session.spawn("first", disposable=False)
    await session.switch_branch("other")
    await operation.wait()
    entry = await session.commit_result(operation)
    assert entry is not None
    assert session.image_uuid == "img-uuid-0"
    assert "main" in (await session.history())[1][entry.id]


async def test_pending_run_cannot_spawn_twice(client):
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response())
    pending = ContreeAsyncSession(client, image="base").run("echo")
    await pending
    with pytest.raises(RuntimeError, match="only be used once"):
        await pending
    assert len(client.calls_for("spawn_instance")) == 1


async def test_set_env_before_resume_preserves_existing_keys(client):
    store = AsyncMemoryStore()
    first = ContreeAsyncSession(client, image="base", session_id="s", store=store)
    await first.ensure_ready()
    await first.set_env({"OLD": "value"})
    resumed = ContreeAsyncSession(client, session_id="s", store=store)
    await resumed.set_env({"NEW": "new"})
    assert resumed.env == {"OLD": "value", "NEW": "new"}


async def test_upload_failure_cancels_and_joins_sibling_uploads(client, monkeypatch):
    session = ContreeAsyncSession(client, image="base")
    started = asyncio.Event()
    stopped = asyncio.Event()

    async def upload(file):
        if str(file.path) == "/fail":
            await started.wait()
            raise OSError("upload failed")
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr(session.file_transfer, "upload", upload)
    with pytest.raises(OSError, match="upload failed"):
        await session.file_transfer.prepare_files({"/fail": b"x", "/blocked": b"y"})
    assert stopped.is_set()
