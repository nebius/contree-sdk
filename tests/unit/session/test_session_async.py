import asyncio

import pytest
from contree_client.models import FileResponse, OperationStatus
from contree_client.testing import ContreeAsyncClient

from contree_sdk.exceptions import FailedOperationError
from contree_sdk.session import AsyncOperation, ContreeAsyncSession
from contree_sdk.store import AsyncMemoryStore
from tests.unit.session.factories import operation_response, spawn_response


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
    client.mock("wait_operation", operation_response())
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=AsyncMemoryStore())

    result = await session.run(shell="echo hi")

    assert result.stdout.as_text() == "hi\n"
    assert result.state.exit_code == 0
    entries, _ = await session.history()
    assert [entry.kind for entry in entries] == ["init"]
    assert session.image_uuid == "img-uuid-0"


async def test_run_non_disposable_advances_history_and_pointer(client: ContreeAsyncClient):
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1", exit_code=0))
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=AsyncMemoryStore())

    result = await session.run(shell="echo hi", disposable=False)

    assert result.state.exit_code == 0
    assert session.image_uuid == "img-uuid-1"
    entries, _ = await session.history()
    assert [entry.kind for entry in entries] == ["init", "run"]
    assert entries[-1].exit_code == 0
    assert entries[-1].operation_uuid == "op-1"


async def test_run_nonzero_exit_code_is_not_an_error(client: ContreeAsyncClient):
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(exit_code=1, stdout="", stderr="boom"))
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=AsyncMemoryStore())

    result = await session.run(shell="false")

    assert result.state.exit_code == 1
    assert result.stderr.as_text() == "boom"


async def test_run_operation_failure_without_result_raises(client: ContreeAsyncClient):
    client.mock("spawn_instance", spawn_response())
    client.mock(
        "wait_operation",
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
    client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1"))
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=AsyncMemoryStore())
    await session.run(shell="echo hi", disposable=False)

    await session.create_branch("feature")
    await session.switch_branch("feature")
    assert dict(await session.list_branches()) == {"main": False, "feature": True}
    assert session.image_uuid == "img-uuid-1"

    await session.rollback()
    assert session.image_uuid == "img-uuid-0"


async def test_set_cwd_and_set_env_persist_through_store(client: ContreeAsyncClient):
    store = AsyncMemoryStore()
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=store, session_id="s1")

    await session.set_cwd("/app")
    await session.set_env({"FOO": "1", "BAR": "2"})

    assert session.cwd == "/app"
    assert session.env == {"FOO": "1", "BAR": "2"}
    metadata = await store.get_session_metadata("s1")
    assert metadata.cwd == "/app"
    assert metadata.env == {"FOO": "1", "BAR": "2"}

    await session.set_env({"BAR": None})
    assert session.env == {"FOO": "1"}
    assert (await store.get_session_metadata("s1")).env == {"FOO": "1"}

    resumed = ContreeAsyncSession(client, image="tag:python:3.11", store=store, session_id="s1")
    await resumed.ensure_ready()
    assert resumed.cwd == "/app"
    assert resumed.env == {"FOO": "1"}


async def test_run_non_disposable_with_files_records_them_on_the_entry(client: ContreeAsyncClient):
    client.mock("ensure_file", FileResponse(uuid="file-uuid-1", sha256="deadbeef", size=4))
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1", exit_code=0))
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

    async with session.run(shell="sleep 600") as operation:
        assert isinstance(operation, AsyncOperation)
        assert operation.uuid == "op-1"

    # disposable (default) run: entering/exiting the context manager alone must not commit
    entries, _ = await session.history()
    assert [entry.kind for entry in entries] == ["init"]


async def test_run_as_async_context_manager_commits_on_clean_success_exit(client: ContreeAsyncClient):
    client.mock("spawn_instance", spawn_response())
    client.mock("follow_operation_events", [])
    client.mock("operation_subprocess_kill", None)
    client.mock("cancel_operation", None)
    client.mock("get_operation_status", operation_response(result_image_uuid="img-uuid-1", exit_code=0))
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=AsyncMemoryStore())

    async with session.run(shell="echo hi", disposable=False):
        pass

    entries, _ = await session.history()
    assert [entry.kind for entry in entries] == ["init", "run"]
    assert entries[-1].image_uuid == "img-uuid-1"
    assert session.image_uuid == "img-uuid-1"
