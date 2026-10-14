"""Command environment overlays remain isolated from persisted session defaults."""

import inspect

import pytest
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk import ContreeAsyncSession, ContreeSession, RunRequest
from tests.unit.session.factories import mock_completion, operation_response, spawn_response


async def call(target, method, *args, **kwargs):
    result = getattr(target, method)(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


@pytest.fixture(params=[False, True], ids=["sync", "async"])
async def session(request):
    instance: ContreeSession | ContreeAsyncSession
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
    await call(instance, "set_env", {"A": "session", "B": "kept"})
    yield instance
    await call(instance.store, "close")


@pytest.mark.parametrize("env", [None, {}, {"A": "command", "C": "new"}])
@pytest.mark.parametrize("disposable", [False, True])
@pytest.mark.parametrize("preserve_env", [False, True])
async def test_command_overlay_reaches_transport_and_keeps_session_defaults(session, env, disposable, preserve_env):
    mock_completion(session.client, operation_response())
    original = None if env is None else dict(env)
    await call(session, "run", "command", env=env, disposable=disposable, preserve_env=preserve_env)
    sent = session.client.calls_for("spawn_instance")[0].kwargs
    assert sent["env"] == {"A": "session", "B": "kept", **(env or {})}
    assert sent["preserve_env"] is preserve_env
    assert session.env == {"A": "session", "B": "kept"}
    assert env == original
    metadata = await call(session.store, "get_session_metadata", session.session_id)
    assert metadata.env == session.env
    resumed = type(session)(session.client, store=session.store, session_id=session.session_id)
    if isinstance(resumed, ContreeAsyncSession):
        await resumed.ensure_ready()
    assert resumed.env == session.env


async def test_effective_environment_is_frozen_at_spawn(session):
    env = {"A": "command"}
    request = RunRequest(command="command", env=env)
    operation = await call(session, "spawn_request", request)
    env["A"] = "changed"
    await call(session, "set_env", {"B": "later"})
    assert dict(operation.context.request.env) == {"A": "command", "B": "kept"}
    assert request.env is not None
    assert dict(request.env) == {"A": "command"}


async def test_empty_environment_and_custom_merge_hook(session, monkeypatch):
    await call(session, "set_env", {"A": None, "B": None})
    assert session.prepare_request(RunRequest(command="command")).env is None
    assert session.prepare_request(RunRequest(command="command", env={})).env == {}
    monkeypatch.setattr(session, "prepare_environment", lambda env: {"FORCED": "value"})
    operation = await call(session, "spawn", "command", env={"A": "ignored"})
    assert operation.context.request.env == {"FORCED": "value"}
    assert session.client.calls_for("spawn_instance")[0].kwargs["env"] == {"FORCED": "value"}
