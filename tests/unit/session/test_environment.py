"""Execution defaults follow the selected session history."""

import inspect
from copy import deepcopy

import pytest
from contree_client.models import InstanceResourcesLimits
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk import AsyncLazySession, ContreeAsyncSession, ContreeSession, LazySession, RunRequest
from contree_sdk.store import Node
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
    await call(
        instance, "change_resources_limits", InstanceResourcesLimits(cpu=2, memory_mib=2048, max_layer_bytes=1024**3)
    )
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
    defaults = session.resources_limits
    await call(
        session,
        "run",
        "command",
        cwd="/command",
        env=env,
        disposable=disposable,
        preserve_env=preserve_env,
        resources_limits=InstanceResourcesLimits(cpu=1),
    )
    sent = session.client.calls_for("spawn_instance")[0].kwargs
    assert sent["cwd"] == "/command"
    assert sent["resources_limits"] == InstanceResourcesLimits(cpu=1)
    assert session.resources_limits == defaults
    assert sent["env"] == {"A": "session", "B": "kept", **(env or {})}
    assert sent["preserve_env"] is preserve_env
    assert session.cwd == "/app"
    assert session.env == {"A": "session", "B": "kept"}
    assert env == original
    node = await call(session.store, "get_node", session.session_id, session.tip_id)
    assert node.data["cwd"] == "/app"
    assert node.data["env"] == session.env
    assert node.data["resources_limits"] == defaults.to_dict()
    resumed = type(session)(session.client, store=session.store, session_id=session.session_id)
    if isinstance(resumed, ContreeAsyncSession):
        await resumed.ensure_ready()
    assert resumed.cwd == "/app"
    assert resumed.env == session.env
    assert resumed.resources_limits == defaults


@pytest.mark.parametrize("method", ["run", "spawn"])
@pytest.mark.parametrize(
    ("options", "expected"), [({}, False), ({"preserve_cwd": True}, True)], ids=["default", "enabled"]
)
async def test_image_workdir_preservation_reaches_transport(session, method, options, expected):
    mock_completion(session.client, operation_response())

    await call(session, method, shell=":", cwd="/work", **options)

    sent = session.client.calls_for("spawn_instance")[0].kwargs
    assert sent["preserve_cwd"] is expected


async def test_lazy_command_rejects_image_workdir_preservation_before_start(session):
    lazy = AsyncLazySession(session) if isinstance(session, ContreeAsyncSession) else LazySession(session)

    with pytest.raises(ValueError, match="preserve_cwd"):
        await call(lazy, "execute", RunRequest(shell=":", preserve_cwd=True))

    assert not session.client.calls_for("spawn_instance")


async def test_navigation_restores_saved_defaults(session):
    entries, _ = await call(session, "history")
    root_id = entries[0].id
    await call(session, "set_cwd", "/app")
    await call(session, "create_branch", "baseline")
    defaults = session.resources_limits
    changed = InstanceResourcesLimits(memory_mib=4096)
    await call(session, "change_resources_limits", changed)
    await call(session, "set_cwd", "/other")
    await call(session, "set_env", {"A": "changed", "B": None, "C": "added"})
    changed_id = session.tip_id

    await call(session, "rollback", 3)
    assert session.resources_limits == defaults
    assert session.cwd == "/app"
    assert session.env == {"A": "session", "B": "kept"}

    await call(session, "navigate_forward", 3)
    assert session.resources_limits == changed
    assert session.cwd == "/other"
    assert session.env == {"A": "changed", "C": "added"}

    await call(session, "switch_branch", "baseline")
    assert session.resources_limits == defaults
    assert session.cwd == "/app"
    assert session.env == {"A": "session", "B": "kept"}

    await call(session, "navigate", root_id)
    assert session.cwd is None
    assert session.resources_limits is None
    assert session.env == {}

    await call(session, "navigate", changed_id)
    operation = await call(session, "spawn", "command")
    assert operation.context.request.cwd == "/other"
    assert operation.context.request.resources_limits == changed
    assert operation.context.request.env == {"A": "changed", "C": "added"}


async def test_history_defaults_are_detached_from_session_and_store(session):
    await call(session, "set_cwd", "/app")
    entry = await call(session, "get_entry", session.tip_id)
    assert entry.cwd == "/app"
    assert entry.env == {"A": "session", "B": "kept"}

    await call(session, "refresh_from_entry", entry)
    session.env["A"] = "session-only"
    session.resources_limits.cpu = 1
    assert entry.resources_limits.cpu == 2
    assert entry.env == {"A": "session", "B": "kept"}
    entry.env["B"] = "entry-only"
    entry.resources_limits.memory_mib = 4096
    assert session.resources_limits.memory_mib == 2048
    assert session.env == {"A": "session-only", "B": "kept"}
    saved = await call(session, "get_entry", entry.id)
    assert saved.env == {"A": "session", "B": "kept"}
    assert saved.resources_limits == InstanceResourcesLimits(cpu=2, memory_mib=2048, max_layer_bytes=1024**3)


@pytest.mark.parametrize(
    ("overrides", "expected_cwd", "expected_env"),
    [
        ({"cwd": "/override"}, "/override", {"A": "session", "B": "kept"}),
        ({"env": {}}, "/app", {}),
        ({"resources_limits": InstanceResourcesLimits(cpu=1)}, "/app", {"A": "session", "B": "kept"}),
        ({"resources_limits": InstanceResourcesLimits()}, "/app", {"A": "session", "B": "kept"}),
        ({"cwd": "/override", "env": {"X": "new"}}, "/override", {"X": "new"}),
    ],
)
async def test_resume_overrides_apply_only_at_initialization(session, overrides, expected_cwd, expected_env):
    await call(session, "set_cwd", "/app")
    saved_id = session.tip_id
    defaults = session.resources_limits
    resumed = type(session)(session.client, store=session.store, session_id=session.session_id, **overrides)
    if isinstance(resumed, ContreeAsyncSession):
        await resumed.ensure_ready()
    assert resumed.cwd == expected_cwd
    assert resumed.resources_limits == overrides.get("resources_limits", defaults)
    assert resumed.env == expected_env

    await call(resumed, "navigate", saved_id)
    assert resumed.resources_limits == defaults
    assert resumed.cwd == "/app"
    assert resumed.env == {"A": "session", "B": "kept"}


async def test_effective_environment_is_frozen_at_spawn(session):
    env = {"A": "command"}
    limits = InstanceResourcesLimits(cpu=1)
    request = RunRequest(command="command", env=env, resources_limits=limits)
    operation = await call(session, "spawn_request", request)
    env["A"] = "changed"
    limits.cpu = 4
    session.resources_limits.memory_mib = 4096
    await call(session, "set_env", {"B": "later"})
    assert dict(operation.context.request.env) == {"A": "command", "B": "kept"}
    assert operation.context.request.resources_limits == InstanceResourcesLimits(cpu=1)
    assert operation.context.session_resources_limits == InstanceResourcesLimits(
        cpu=2, memory_mib=2048, max_layer_bytes=1024**3
    )
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


async def test_legacy_history_without_resources_uses_service_defaults(session):
    node = Node(id="legacy", parent_id=session.tip_id, kind="config", data={"image_uuid": "base"})
    await call(session.store, "append", session.session_id, node)
    await call(session, "navigate", node.id)
    assert session.resources_limits is None
    operation = await call(session, "spawn", "command")
    assert operation.context.request.resources_limits is None
    assert session.client.calls_for("spawn_instance")[0].kwargs["resources_limits"] is Ellipsis


@pytest.mark.parametrize("limits", [None, InstanceResourcesLimits(), InstanceResourcesLimits(cpu=1)])
async def test_change_resources_limits_replaces_and_persists_defaults(session, limits):
    parent_id = session.tip_id
    supplied = deepcopy(limits)
    await call(session, "change_resources_limits", supplied)
    entry = await call(session, "get_entry", session.tip_id)
    assert (entry.kind, entry.parent_id, entry.resources_limits) == ("config", parent_id, limits)
    if supplied is not None:
        supplied.cpu = 4
    resumed = type(session)(session.client, store=session.store, session_id=session.session_id)
    if isinstance(resumed, ContreeAsyncSession):
        await resumed.ensure_ready()
    assert resumed.resources_limits == limits
    assert session.resources_limits == limits
    assert not session.client.calls_for("spawn_instance")
    await call(session, "rollback")
    assert session.resources_limits == InstanceResourcesLimits(cpu=2, memory_mib=2048, max_layer_bytes=1024**3)
