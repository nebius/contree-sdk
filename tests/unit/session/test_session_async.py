import pytest
from contree_client.models import OperationStatus
from contree_client.testing import ContreeAsyncClient

from contree_sdk.exceptions import FailedOperationError
from contree_sdk.session import ContreeAsyncSession
from contree_sdk.store import MemoryStore
from tests.unit.session.factories import operation_response, spawn_response


@pytest.fixture
def client() -> ContreeAsyncClient:
    client = ContreeAsyncClient()
    client.mock("resolve_image", "img-uuid-0")
    return client


async def test_construct_resolves_image_and_seeds_history(client: ContreeAsyncClient):
    store = MemoryStore()
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=store)

    await session.ensure_ready()
    assert session.image_uuid == "img-uuid-0"
    entries, _ = await session.history()
    assert [entry.kind for entry in entries] == ["init"]


def test_construct_requires_image_or_session_id(client: ContreeAsyncClient):
    with pytest.raises(ValueError):
        ContreeAsyncSession(client)


async def test_construct_resumes_from_existing_session(client: ContreeAsyncClient):
    store = MemoryStore()
    first = ContreeAsyncSession(client, image="tag:python:3.11", store=store, session_id="my-session")
    await first.ensure_ready()

    resumed = ContreeAsyncSession(client, store=store, session_id="my-session")
    await resumed.ensure_ready()
    assert resumed.image_uuid == first.image_uuid
    assert resumed.tip_id == first.tip_id


async def test_run_disposable_does_not_advance_history(client: ContreeAsyncClient):
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response())
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=MemoryStore())

    result = await session.run(shell="echo hi")

    assert result.stdout.as_text() == "hi\n"
    assert result.state.exit_code == 0
    entries, _ = await session.history()
    assert [entry.kind for entry in entries] == ["init"]
    assert session.image_uuid == "img-uuid-0"


async def test_run_non_disposable_advances_history_and_pointer(client: ContreeAsyncClient):
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1", exit_code=0))
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=MemoryStore())

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
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=MemoryStore())

    result = await session.run(shell="false")

    assert result.state.exit_code == 1
    assert result.stderr.as_text() == "boom"


async def test_run_operation_failure_without_result_raises(client: ContreeAsyncClient):
    client.mock("spawn_instance", spawn_response())
    client.mock(
        "wait_operation",
        operation_response(status=OperationStatus.FAILED, error="vm could not start", with_result=False),
    )
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=MemoryStore())

    with pytest.raises(FailedOperationError):
        await session.run(shell="echo hi")


async def test_run_requires_command_or_shell(client: ContreeAsyncClient):
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=MemoryStore())
    with pytest.raises(ValueError):
        await session.run()


async def test_run_rejects_both_command_and_shell(client: ContreeAsyncClient):
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=MemoryStore())
    with pytest.raises(ValueError):
        await session.run(command="echo hi", shell="echo hi")


async def test_branch_and_rollback_update_live_pointer(client: ContreeAsyncClient):
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1"))
    session = ContreeAsyncSession(client, image="tag:python:3.11", store=MemoryStore())
    await session.run(shell="echo hi", disposable=False)

    await session.create_branch("feature")
    await session.switch_branch("feature")
    assert dict(await session.list_branches()) == {"main": False, "feature": True}
    assert session.image_uuid == "img-uuid-1"

    await session.rollback()
    assert session.image_uuid == "img-uuid-0"
