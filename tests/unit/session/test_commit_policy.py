"""Commit decisions are identical for automatic runs and explicit completion."""

import inspect

import pytest
from contree_client.models import InstanceResult, InstanceResultState, OperationInstanceMetadata, OperationStatus
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk import ContreeAsyncSession, ContreeSession
from contree_sdk.exceptions import FailedOperationError
from contree_sdk.session import AbstractCommitPolicy, ApiSuccessCommitPolicy, ZeroExitCommitPolicy
from tests.unit.session.factories import mock_completion, operation_response, spawn_response


async def call(target, method, *args, **kwargs):
    result = getattr(target, method)(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


@pytest.fixture(params=[False, True], ids=["sync", "async"])
async def session(request):
    instance: ContreeAsyncSession | ContreeSession
    if request.param:
        client = ContreeAsyncClient()
        client.mock("resolve_image", "base")
        client.mock("spawn_instance", spawn_response())
        instance = ContreeAsyncSession(client, image="base")
        await instance.ensure_ready()
    else:
        sync_client = ContreeClient()
        sync_client.mock("resolve_image", "base")
        sync_client.mock("spawn_instance", spawn_response())
        instance = ContreeSession(sync_client, image="base")
    yield instance
    await call(instance.store, "close")


@pytest.mark.parametrize("explicit", [False, True], ids=["run", "spawn-wait-commit"])
@pytest.mark.parametrize("policy", [None, ApiSuccessCommitPolicy(), ZeroExitCommitPolicy()])
@pytest.mark.parametrize("exit_code", [0, 7, None])
async def test_policy_controls_commit_without_changing_result(session, explicit, policy, exit_code):
    if policy is None:
        session = type(session)(session.client, store=session.store, session_id=session.session_id)
    else:
        session.commit_policy = policy
    response = operation_response()
    assert isinstance(response.metadata, OperationInstanceMetadata)
    assert isinstance(response.metadata.result, InstanceResult)
    response.metadata.result.state = InstanceResultState(exit_code=exit_code if exit_code is not None else ...)
    mock_completion(session.client, response)
    if explicit:
        operation = await call(session, "spawn", "command", disposable=False)
        result = await call(operation, "wait")
        entry = await call(session, "commit_result", operation)
    else:
        result = await call(session, "run", "command", disposable=False)
    committed = not isinstance(policy, ZeroExitCommitPolicy) or exit_code == 0
    entries, _ = await call(session, "history")
    assert len(entries) == (2 if committed else 1)
    assert session.image_uuid == ("img-uuid-1" if committed else "base")
    assert result is response.metadata.result
    if explicit:
        assert (entry is not None) == committed


@pytest.mark.parametrize(
    ("status", "error"), [(OperationStatus.FAILED, FailedOperationError), (OperationStatus.CANCELLED, InterruptedError)]
)
async def test_api_failure_cannot_be_accepted_by_policy(session, status, error):
    class UnexpectedPolicy(AbstractCommitPolicy):
        def should_commit(self, context, result):
            pytest.fail("policy must not receive an unsuccessful API result")

    session.commit_policy = UnexpectedPolicy()
    mock_completion(session.client, operation_response(status=status, result_image_uuid=None))
    operation = await call(session, "spawn", "command", disposable=False)
    await call(operation, "status")
    with pytest.raises(error):
        await call(session, "commit_result", operation)
    assert len((await call(session, "history"))[0]) == 1


async def test_custom_policy_receives_effective_context_and_result(session):
    seen = []

    class CustomPolicy(AbstractCommitPolicy):
        def should_commit(self, context, result):
            seen.append((context, result))
            return False

    session.commit_policy = CustomPolicy()
    mock_completion(session.client, operation_response())
    operation = await call(session, "spawn", "command", disposable=False)
    result = await call(operation, "wait")
    before = await call(session.store, "read_session", session.session_id)
    assert await call(session, "commit_result", operation, branch="rejected") is None
    assert seen == [(operation.context, result)]
    assert await call(session.store, "read_session", session.session_id) == before


async def test_disposable_result_never_invokes_policy_or_commits(session):
    class UnexpectedPolicy(AbstractCommitPolicy):
        def should_commit(self, context, result):
            pytest.fail("disposable results cannot be retained")

    session.commit_policy = UnexpectedPolicy()
    mock_completion(session.client, operation_response())
    operation = await call(session, "spawn", "command")
    await call(operation, "wait")
    assert await call(session, "commit_result", operation) is None
    assert len((await call(session, "history"))[0]) == 1


async def test_accepted_result_requires_image(session):
    mock_completion(session.client, operation_response(result_image_uuid=None))
    with pytest.raises(ValueError, match="no result image"):
        await call(session, "run", "command", disposable=False)
    assert len((await call(session, "history"))[0]) == 1
