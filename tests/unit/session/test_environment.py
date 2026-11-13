"""Working directory and environment defaults follow the selected session history."""

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
    await call(session, "set_cwd", "/app")
    original = None if env is None else dict(env)
    await call(session, "run", "command", cwd="/command", env=env, disposable=disposable, preserve_env=preserve_env)
    sent = session.client.calls_for("spawn_instance")[0].kwargs
    assert sent["cwd"] == "/command"
    assert sent["env"] == {"A": "session", "B": "kept", **(env or {})}
    assert sent["preserve_env"] is preserve_env
    assert session.cwd == "/app"
    assert session.env == {"A": "session", "B": "kept"}
    assert env == original
    node = await call(session.store, "get_node", session.session_id, session.tip_id)
    assert node.data["cwd"] == "/app"
    assert node.data["env"] == session.env
    resumed = type(session)(session.client, store=session.store, session_id=session.session_id)
    if isinstance(resumed, ContreeAsyncSession):
        await resumed.ensure_ready()
    assert resumed.cwd == "/app"
    assert resumed.env == session.env


async def test_navigation_restores_saved_defaults(session):
    entries, _ = await call(session, "history")
    root_id = entries[0].id
    await call(session, "set_cwd", "/app")
    await call(session, "create_branch", "baseline")
    await call(session, "set_cwd", "/other")
    await call(session, "set_env", {"A": "changed", "B": None, "C": "added"})
    changed_id = session.tip_id

    await call(session, "rollback", 2)
    assert session.cwd == "/app"
    assert session.env == {"A": "session", "B": "kept"}

    await call(session, "navigate_forward", 2)
    assert session.cwd == "/other"
    assert session.env == {"A": "changed", "C": "added"}

    await call(session, "switch_branch", "baseline")
    assert session.cwd == "/app"
    assert session.env == {"A": "session", "B": "kept"}

    await call(session, "navigate", root_id)
    assert session.cwd is None
    assert session.env == {}

    await call(session, "navigate", changed_id)
    operation = await call(session, "spawn", "command")
    assert operation.context.request.cwd == "/other"
    assert operation.context.request.env == {"A": "changed", "C": "added"}


async def test_history_defaults_are_detached_from_session_and_store(session):
    await call(session, "set_cwd", "/app")
    entry = await call(session, "get_entry", session.tip_id)
    assert entry.cwd == "/app"
    assert entry.env == {"A": "session", "B": "kept"}

    await call(session, "refresh_from_entry", entry)
    session.env["A"] = "session-only"
    assert entry.env == {"A": "session", "B": "kept"}
    entry.env["B"] = "entry-only"
    assert session.env == {"A": "session-only", "B": "kept"}
    saved = await call(session, "get_entry", entry.id)
    assert saved.env == {"A": "session", "B": "kept"}


@pytest.mark.parametrize(
    ("overrides", "expected_cwd", "expected_env"),
    [
        ({"cwd": "/override"}, "/override", {"A": "session", "B": "kept"}),
        ({"env": {}}, "/app", {}),
        ({"cwd": "/override", "env": {"X": "new"}}, "/override", {"X": "new"}),
    ],
)
async def test_resume_overrides_apply_only_at_initialization(session, overrides, expected_cwd, expected_env):
    await call(session, "set_cwd", "/app")
    saved_id = session.tip_id
    resumed = type(session)(session.client, store=session.store, session_id=session.session_id, **overrides)
    if isinstance(resumed, ContreeAsyncSession):
        await resumed.ensure_ready()
    assert resumed.cwd == expected_cwd
    assert resumed.env == expected_env

    await call(resumed, "navigate", saved_id)
    assert resumed.cwd == "/app"
    assert resumed.env == {"A": "session", "B": "kept"}


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
    assert (await call(session, "prepare_request", RunRequest(command="command"))).env is None
    assert (await call(session, "prepare_request", RunRequest(command="command", env={}))).env == {}
    monkeypatch.setattr(session, "prepare_environment", lambda env: {"FORCED": "value"})
    operation = await call(session, "spawn", "command", env={"A": "ignored"})
    assert operation.context.request.env == {"FORCED": "value"}
    assert session.client.calls_for("spawn_instance")[0].kwargs["env"] == {"FORCED": "value"}
