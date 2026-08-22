import pytest
from contree_client.models import OperationStatus
from contree_client.testing import ContreeClient

from contree_sdk.exceptions import FailedOperationError
from contree_sdk.session import ContreeSession
from contree_sdk.store import SyncMemoryStore
from tests.unit.session.factories import operation_response, spawn_response


@pytest.fixture
def client() -> ContreeClient:
    client = ContreeClient()
    client.mock("resolve_image", "img-uuid-0")
    return client


def test_construct_resolves_image_and_seeds_history(client: ContreeClient):
    store = SyncMemoryStore()
    session = ContreeSession(client, image="tag:python:3.11", store=store)

    assert session.image_uuid == "img-uuid-0"
    entries, _ = session.history()
    assert [entry.kind for entry in entries] == ["init"]


def test_construct_requires_image_or_session_id(client: ContreeClient):
    with pytest.raises(ValueError):
        ContreeSession(client)


def test_construct_resumes_from_existing_session(client: ContreeClient):
    store = SyncMemoryStore()
    first = ContreeSession(client, image="tag:python:3.11", store=store, session_id="my-session")

    resumed = ContreeSession(client, store=store, session_id="my-session")
    assert resumed.image_uuid == first.image_uuid
    assert resumed.tip_id == first.tip_id


def test_run_disposable_does_not_advance_history(client: ContreeClient):
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response())
    session = ContreeSession(client, image="tag:python:3.11", store=SyncMemoryStore())

    result = session.run(shell="echo hi")

    assert result.stdout.as_text() == "hi\n"
    assert result.state.exit_code == 0
    entries, _ = session.history()
    assert [entry.kind for entry in entries] == ["init"]
    assert session.image_uuid == "img-uuid-0"


def test_run_non_disposable_advances_history_and_pointer(client: ContreeClient):
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1", exit_code=0))
    session = ContreeSession(client, image="tag:python:3.11", store=SyncMemoryStore())

    result = session.run(shell="echo hi", disposable=False)

    assert result.state.exit_code == 0
    assert session.image_uuid == "img-uuid-1"
    entries, _ = session.history()
    assert [entry.kind for entry in entries] == ["init", "run"]
    assert entries[-1].exit_code == 0
    assert entries[-1].operation_uuid == "op-1"


def test_run_nonzero_exit_code_is_not_an_error(client: ContreeClient):
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(exit_code=1, stdout="", stderr="boom"))
    session = ContreeSession(client, image="tag:python:3.11", store=SyncMemoryStore())

    result = session.run(shell="false")

    assert result.state.exit_code == 1
    assert result.stderr.as_text() == "boom"


def test_run_operation_failure_without_result_raises(client: ContreeClient):
    client.mock("spawn_instance", spawn_response())
    client.mock(
        "wait_operation",
        operation_response(status=OperationStatus.FAILED, error="vm could not start", with_result=False),
    )
    session = ContreeSession(client, image="tag:python:3.11", store=SyncMemoryStore())

    with pytest.raises(FailedOperationError):
        session.run(shell="echo hi")


def test_run_requires_command_or_shell(client: ContreeClient):
    session = ContreeSession(client, image="tag:python:3.11", store=SyncMemoryStore())
    with pytest.raises(ValueError):
        session.run()


def test_run_rejects_both_command_and_shell(client: ContreeClient):
    session = ContreeSession(client, image="tag:python:3.11", store=SyncMemoryStore())
    with pytest.raises(ValueError):
        session.run(command="echo hi", shell="echo hi")


def test_branch_and_rollback_update_live_pointer(client: ContreeClient):
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1"))
    session = ContreeSession(client, image="tag:python:3.11", store=SyncMemoryStore())
    session.run(shell="echo hi", disposable=False)

    session.create_branch("feature")
    session.switch_branch("feature")
    assert dict(session.list_branches()) == {"main": False, "feature": True}
    assert session.image_uuid == "img-uuid-1"

    session.rollback()
    assert session.image_uuid == "img-uuid-0"
