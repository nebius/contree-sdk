"""Network configuration survives history, VM boundaries and Store reopening."""

import asyncio
import inspect

import pytest
from contree_client.models import InstanceNetworking, NetworkPolicyTag
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk import AsyncLazySession, ContreeAsyncSession, ContreeSession, LazySession, create_sandbox_session
from contree_sdk.execution import RunRequest
from contree_sdk.files import AsyncClientFileTransfer, UploadedFile, UploadFileSpec
from contree_sdk.session import AbstractSnapshotPolicy
from contree_sdk.store import AsyncSQLiteStore, Node, SyncSQLiteStore
from tests.unit.session.factories import mock_completion, operation_response, spawn_response
from tests.unit.session.lazy_clients import LiveAsyncClient, LiveClient


POLICY_A = "11111111-1111-4111-8111-111111111111"
POLICY_B = "22222222-2222-4222-8222-222222222222"


class ManualSnapshotPolicy(AbstractSnapshotPolicy):
    def notify(self, event):
        super().notify(event)


async def invoke(function, *args, **kwargs):
    result = function(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


async def entry_data(session, entry):
    node = await invoke(session.store.get_node, session.session_id, entry.id)
    return node.data


@pytest.fixture(params=[False, True], ids=["sync", "async"])
async def session(request, tmp_path):
    instance: ContreeAsyncSession | ContreeSession
    store: AsyncSQLiteStore | SyncSQLiteStore
    client: ContreeAsyncClient | ContreeClient
    if request.param:
        client = ContreeAsyncClient()
        client.mock("get_network_policy")
        store = AsyncSQLiteStore(tmp_path / "session.db")
        client.mock("resolve_image", "base")
        instance = ContreeAsyncSession(
            client, image="base", store=store, network_policy=POLICY_A, network_enabled=False
        )
        await instance.ensure_ready()
    else:
        client = ContreeClient()
        client.mock("get_network_policy")
        store = SyncSQLiteStore(tmp_path / "session.db")
        client.mock("resolve_image", "base")
        instance = ContreeSession(client, image="base", store=store, network_policy=POLICY_A, network_enabled=False)
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response())
    try:
        yield instance
    finally:
        await invoke(store.close)


async def test_change_network_enabled_rejects_none_without_changing_defaults(session):
    tip = session.tip_id
    calls = list(session.client.calls)

    with pytest.raises(TypeError, match="bool"):
        await invoke(session.change_network_enabled, None)

    assert session.network_enabled is False
    assert session.network_policy_uuids == (POLICY_A,)
    assert session.tip_id == tip
    assert session.client.calls == calls


async def test_initial_settings_and_independent_changes_survive_reopen(session, tmp_path):
    entries, _ = await invoke(session.history)
    assert entries[0].kind == "init"
    assert entries[0].network_policy_uuids == (POLICY_A,)
    assert entries[0].network_enabled is False
    saved_data = await entry_data(session, entries[0])
    assert saved_data["network_policy_uuids"] == [POLICY_A]
    assert saved_data["network_enabled"] is False

    await invoke(session.change_network_enabled, True)
    await invoke(session.change_network_policy, POLICY_B)
    await invoke(session.change_network_enabled, False)
    assert session.network_policy_uuids == (POLICY_B,)
    await invoke(session.change_network_policy, None)
    assert session.network_enabled is False

    entries, _ = await invoke(session.history)
    assert [entry.kind for entry in entries] == ["init", "config", "config", "config", "config"]
    assert {entry.image_uuid for entry in entries} == {"base"}
    stored = [await entry_data(session, entry) for entry in entries]
    assert [(data["network_policy_uuids"], data["network_enabled"]) for data in stored] == [
        ([POLICY_A], False),
        ([POLICY_A], True),
        ([POLICY_B], True),
        ([POLICY_B], False),
        ([], False),
    ]
    await invoke(session.store.close)
    store = type(session.store)(tmp_path / "session.db")
    try:
        restored = type(session)(session.client, session_id=session.session_id, store=store)
        if isinstance(restored, ContreeAsyncSession):
            await restored.ensure_ready()
        assert restored.network_policy_uuids == ()
        assert restored.network_enabled is False
        await invoke(restored.navigate, entries[2].id)
        assert restored.network_policy_uuids == (POLICY_B,)
        assert restored.network_enabled is True
        await invoke(restored.rollback)
        assert restored.network_policy_uuids == (POLICY_A,)
        await invoke(restored.navigate_forward)
        assert restored.network_policy_uuids == (POLICY_B,)
    finally:
        await invoke(store.close)


async def test_runs_and_staging_carry_network_state(session):
    await invoke(session.change_network_enabled, True)
    staged = await invoke(session.stage_files, {"/data": UploadFileSpec(source=UploadedFile("upload", "a" * 64))})
    saved_data = await entry_data(session, staged)
    assert saved_data["network_policy_uuids"] == [POLICY_A]
    await invoke(session.run, "first")
    await invoke(session.change_network_policy, None)
    await invoke(session.run, "second")
    calls = session.client.calls_for("spawn_instance")
    assert calls[0].kwargs["networking"].to_dict() == {"enabled": True, "policy": [POLICY_A]}
    assert calls[1].kwargs["networking"].to_dict() == {"enabled": True, "policy": []}
    entries, _ = await invoke(session.history)
    runs = [entry for entry in entries if entry.kind == "run"]
    stored = [await entry_data(session, entry) for entry in runs]
    assert [data["network_policy_uuids"] for data in stored] == [[POLICY_A], []]


async def test_branch_switch_restores_networking_and_late_result_does_not_overwrite_it(session):
    operation = await invoke(session.spawn, "first")
    await invoke(session.create_branch, "other")
    await invoke(session.switch_branch, "other")
    await invoke(session.change_network_policy, POLICY_B)
    await invoke(session.change_network_enabled, True)
    await invoke(operation.wait)
    entry = await invoke(session.commit_result, operation)
    saved_data = await entry_data(session, entry)
    assert saved_data["network_policy_uuids"] == [POLICY_A]
    assert saved_data["network_enabled"] is False
    assert session.network_policy_uuids == (POLICY_B,)
    await invoke(session.switch_branch, "main")
    assert session.network_policy_uuids == (POLICY_A,)
    assert session.network_enabled is False
    await invoke(operation.shutdown)


@pytest.mark.parametrize("session", [True], indirect=True, ids=["async"])
@pytest.mark.parametrize("action", ["commit", "detached_commit", "wait_operation", "stage_files"])
@pytest.mark.parametrize("navigation", ["navigate", "switch_branch"])
async def test_navigation_during_refresh_keeps_network_selection_consistent(session, monkeypatch, action, navigation):
    selected_id = session.tip_id
    await session.create_branch("selected")
    await session.change_network_policy(POLICY_B)
    await session.change_network_enabled(True)
    source_id = session.tip_id
    operation = None
    if action != "stage_files":
        operation = await session.spawn("command")
        if action in {"detached_commit", "wait_operation"}:
            await session.detach(operation)
        if action in {"commit", "detached_commit"}:
            await operation.wait()

    navigation_task: asyncio.Task[None] | None = None
    refresh_from_entry = session.refresh_from_entry
    get_node = session.store.get_node

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
    monkeypatch.setattr(session.store, "get_node", read_after_navigation)

    if action == "stage_files":
        await session.stage_files({"/data": UploadFileSpec(source=UploadedFile("upload", "a" * 64))})
    else:
        assert operation is not None
        if action == "wait_operation":
            await session.wait_operation(operation.uuid)
        else:
            await session.commit_result(operation)
    assert navigation_task is not None
    await navigation_task

    assert session.tip_id == selected_id
    assert session.image_uuid == "base"
    assert session.network_policy_uuids == (POLICY_A,)
    assert session.network_enabled is False
    selected_branch = "main" if navigation == "navigate" else "selected"
    entries, branches = await session.history()
    assert selected_branch in branches[selected_id]
    saved = [entry for entry in entries if entry.parent_id == source_id]
    assert len(saved) == 1
    assert saved[0].network_policy_uuids == (POLICY_B,)
    assert saved[0].network_enabled is True


async def test_legacy_history_entry_restores_default_networking_without_policy_lookups(session):
    node = Node(id="legacy", parent_id=session.tip_id, kind="run", data={"image_uuid": "legacy-image"})
    await invoke(session.store.append, session.session_id, node)
    entry = await invoke(session.get_entry, node.id)
    assert entry.network_enabled is True
    assert entry.network_policy_uuids == ()
    calls = list(session.client.calls)

    await invoke(session.navigate, entry.id)

    assert session.tip_id == entry.id
    assert session.image_uuid == "legacy-image"
    assert session.network_enabled is True
    assert session.network_policy_uuids == ()
    assert session.client.calls == calls


@pytest.mark.parametrize(
    ("policy", "enabled", "expected_policies", "expected_enabled"),
    [(None, None, (POLICY_A,), False), ([], False, (), False), ("tag:temporary", True, (POLICY_B,), True)],
)
async def test_prepare_request_resolves_network_settings_without_spawning(
    session, policy, enabled, expected_policies, expected_enabled
):
    session.client.mock("get_network_policy_tag", NetworkPolicyTag(tag="temporary", uuid=POLICY_B))
    original = RunRequest(command="first", network_policy=policy, network_enabled=enabled)

    prepared = await invoke(session.prepare_request, original)

    assert prepared.network_policy == expected_policies
    assert prepared.network_enabled is expected_enabled
    assert original.network_policy == (() if policy == [] else policy)
    assert original.network_enabled is enabled
    assert session.network_policy_uuids == (POLICY_A,)
    assert session.network_enabled is False
    assert not session.client.calls_for("spawn_instance")


async def test_async_tag_lookup_preserves_submission_context(monkeypatch):
    client = ContreeAsyncClient()
    client.mock("get_network_policy")
    client.mock("resolve_image", "base")
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response())
    session = ContreeAsyncSession(
        client, image="base", cwd="/workspace", env={"MODE": "initial"}, network_policy=POLICY_A, network_enabled=False
    )
    await session.ensure_ready()
    entered = asyncio.Event()
    proceed = asyncio.Event()
    parent_id = session.tip_id

    async def lookup(tag):
        entered.set()
        await proceed.wait()
        return NetworkPolicyTag(tag=tag, uuid=POLICY_B)

    monkeypatch.setattr(session.client, "get_network_policy_tag", lookup)
    spawning = asyncio.create_task(session.spawn("first", network_policy="tag:temporary", network_enabled=True))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await session.change_network_policy(None)
        await session.change_network_enabled(True)
        await session.set_cwd("/later")
        await session.set_env({"MODE": "later"})
        selected_tip = session.tip_id
        proceed.set()
        operation = await asyncio.wait_for(spawning, 2)
        try:
            assert operation.context is not None
            assert operation.context.parent_id == parent_id
            assert operation.context.session_network_policy_uuids == (POLICY_A,)
            assert operation.context.session_network_enabled is False
            assert operation.context.session_cwd == "/workspace"
            assert operation.context.session_env == {"MODE": "initial"}
            assert operation.context.request.cwd == "/workspace"
            assert operation.context.request.env == {"MODE": "initial"}
            assert operation.context.request.network_policy == (POLICY_B,)
            assert operation.context.request.network_enabled is True
            await operation.wait()
            await session.commit_result(operation)
        finally:
            await operation.shutdown()
        assert session.tip_id == selected_tip
        assert session.network_policy_uuids == ()
        assert session.network_enabled is True
    finally:
        proceed.set()
        await spawning
        await session.store.close()


@pytest.mark.parametrize("method", ["run", "spawn"])
@pytest.mark.parametrize(
    ("networking", "expected_enabled", "expected_policy"),
    [
        (InstanceNetworking(enabled=True, policy=[POLICY_B]), True, [POLICY_B]),
        (InstanceNetworking(enabled=False, policy=[]), False, []),
        (InstanceNetworking(enabled=False), False, []),
        (InstanceNetworking(policy=["tag:temporary"]), True, [POLICY_B]),
        (InstanceNetworking(), True, []),
    ],
)
async def test_legacy_networking_overrides_without_changing_defaults(
    session, method, networking, expected_enabled, expected_policy
):
    session.client.mock("get_network_policy_tag", NetworkPolicyTag(tag="temporary", uuid=POLICY_B))
    with pytest.warns(DeprecationWarning, match="networking is deprecated") as warnings:
        result = await invoke(getattr(session, method), "override", networking=networking)
    assert (
        sum(
            warning.category is DeprecationWarning
            and str(warning.message) == "networking is deprecated; use network_enabled and network_policy instead"
            for warning in warnings
        )
        == 1
    )
    if method == "spawn":
        try:
            await invoke(result.wait)
        finally:
            await invoke(result.shutdown)

    assert session.client.calls_for("spawn_instance")[0].kwargs["networking"].to_dict() == {
        "enabled": expected_enabled,
        "policy": expected_policy,
    }
    assert session.network_enabled is False
    assert session.network_policy_uuids == (POLICY_A,)


@pytest.mark.parametrize("method", ["run", "spawn"])
async def test_none_legacy_networking_preserves_new_overrides(session, method):
    result = await invoke(
        getattr(session, method), "override", networking=None, network_enabled=True, network_policy=POLICY_B
    )
    if method == "spawn":
        try:
            await invoke(result.wait)
        finally:
            await invoke(result.shutdown)

    assert session.client.calls_for("spawn_instance")[0].kwargs["networking"].to_dict() == {
        "enabled": True,
        "policy": [POLICY_B],
    }


@pytest.mark.parametrize("method", ["run", "spawn"])
@pytest.mark.parametrize(
    "overrides",
    [
        {"network_enabled": False},
        {"network_enabled": True},
        {"network_policy": []},
        {"network_policy": POLICY_B},
    ],
)
async def test_legacy_networking_rejects_conflicting_arguments_before_io(session, method, overrides):
    calls = list(session.client.calls)
    tip = session.tip_id
    with pytest.raises(ValueError, match="networking cannot be combined"):
        await invoke(
            getattr(session, method),
            "conflict",
            networking=InstanceNetworking(enabled=True, policy=[POLICY_B]),
            **overrides,
        )

    assert session.client.calls == calls
    assert session.tip_id == tip
    assert session.network_enabled is False
    assert session.network_policy_uuids == (POLICY_A,)


@pytest.mark.parametrize(
    ("policy", "enabled", "effective_policies", "effective_enabled"),
    [
        (None, None, (POLICY_A,), False),
        ([], None, (), False),
        (POLICY_B, True, (POLICY_B,), True),
        (None, True, (POLICY_A,), True),
        ([POLICY_A, POLICY_B], False, (POLICY_A, POLICY_B), False),
    ],
)
async def test_operation_overrides_preserve_defaults_and_history(
    session, tmp_path, policy, enabled, effective_policies, effective_enabled
):
    operation = await invoke(session.spawn, "override", network_policy=policy, network_enabled=enabled)
    try:
        assert operation.context.session_network_policy_uuids == (POLICY_A,)
        assert operation.context.session_network_enabled is False
        assert operation.context.request.network_policy == effective_policies
        assert operation.context.request.network_enabled is effective_enabled
        await invoke(operation.wait)
        await invoke(session.commit_result, operation)
    finally:
        await invoke(operation.shutdown)

    assert session.network_policy_uuids == (POLICY_A,)
    assert session.network_enabled is False
    await invoke(session.run, "default")
    calls = session.client.calls_for("spawn_instance")
    assert calls[0].kwargs["networking"].to_dict() == {
        "enabled": effective_enabled,
        "policy": list(effective_policies),
    }
    assert calls[1].kwargs["networking"].to_dict() == {"enabled": False, "policy": [POLICY_A]}

    entries, _ = await invoke(session.history)
    assert [entry.kind for entry in entries] == ["init", "run", "run"]
    overridden = entries[1]
    assert overridden.network_policy_uuids == (POLICY_A,)
    assert overridden.network_enabled is False
    saved_data = await entry_data(session, overridden)
    assert saved_data["network_policy_uuids"] == [POLICY_A]
    assert saved_data["network_enabled"] is False
    await invoke(session.navigate, overridden.id)
    assert session.network_policy_uuids == (POLICY_A,)
    assert session.network_enabled is False

    await invoke(session.store.close)
    store = type(session.store)(tmp_path / "session.db")
    try:
        restored = type(session)(session.client, session_id=session.session_id, node_id=overridden.id, store=store)
        if isinstance(restored, ContreeAsyncSession):
            await restored.ensure_ready()
        assert restored.network_policy_uuids == (POLICY_A,)
        assert restored.network_enabled is False
    finally:
        await invoke(store.close)


async def test_false_override_disables_network_without_changing_true_default(session):
    await invoke(session.change_network_enabled, True)
    await invoke(session.run, "offline", network_enabled=False)
    await invoke(session.run, "online", network_enabled=None)
    assert [call.kwargs["networking"].enabled for call in session.client.calls_for("spawn_instance")] == [False, True]
    assert session.network_enabled is True


@pytest.mark.parametrize(
    ("overrides", "effective_policies", "effective_enabled"),
    [
        ({}, (POLICY_A,), False),
        ({"network_policy": "tag:temporary", "network_enabled": True}, (POLICY_B,), True),
        ({"network_policy": [POLICY_A, "tag:temporary"]}, (POLICY_A, POLICY_B), False),
    ],
    ids=["inherited", "overridden", "multiple-policies"],
)
async def test_detached_completion_preserves_submission_settings(
    session, overrides, effective_policies, effective_enabled
):
    session.client.mock("get_network_policy_tag", NetworkPolicyTag(tag="temporary", uuid=POLICY_B))
    record = await invoke(session.spawn_detached, "first", **overrides)
    assert record.session_network_policy_uuids == (POLICY_A,)
    assert record.session_network_enabled is False
    parent = await invoke(session.get_entry, record.parent_id)
    saved_data = await entry_data(session, parent)
    assert saved_data["network_policy_uuids"] == [POLICY_A]
    assert saved_data["network_enabled"] is False
    assert record.to_dict()["request"]["network_policy"] == list(effective_policies)
    assert record.to_dict()["request"]["network_enabled"] is effective_enabled
    tag_lookups = len(session.client.calls_for("get_network_policy_tag"))
    policy_lookups = len(session.client.calls_for("get_network_policy"))

    await invoke(session.change_network_enabled, True)
    await invoke(session.change_network_policy, None)
    selected_tip = session.tip_id
    restored = type(session)(session.client, store=session.store, session_id=session.session_id)
    await invoke(restored.wait_operation, record.uuid)
    completed = await invoke(restored.get_operation, record.uuid)
    saved = await invoke(restored.get_entry, completed.history_id)
    assert saved.network_policy_uuids == (POLICY_A,)
    assert saved.network_enabled is False
    saved_data = await entry_data(session, saved)
    assert saved_data["network_policy_uuids"] == [POLICY_A]
    assert saved_data["network_enabled"] is False
    assert saved_data["record"]["request"]["network_policy"] == list(effective_policies)
    assert saved_data["record"]["request"]["network_enabled"] is effective_enabled
    assert restored.tip_id == selected_tip
    assert restored.network_policy_uuids == ()
    assert restored.network_enabled is True
    operation = await invoke(restored.restore_operation, record.uuid)
    assert operation.context.session_network_policy_uuids == (POLICY_A,)
    assert operation.context.session_network_enabled is False
    assert operation.context.parent_id == parent.id
    assert operation.context.request.network_policy == effective_policies
    assert operation.context.request.network_enabled is effective_enabled
    assert len(session.client.calls_for("get_network_policy_tag")) == tag_lookups
    assert len(session.client.calls_for("get_network_policy")) == policy_lookups


async def test_multiple_policies_are_resolved_once_and_survive_reopen(session, tmp_path):
    session.client.mock("get_network_policy_tag", NetworkPolicyTag(tag="restricted", uuid=POLICY_B))
    references = [POLICY_A, "tag:restricted", POLICY_B]
    await invoke(session.change_network_policy, references)
    references.clear()
    assert session.network_policy_uuids == (POLICY_A, POLICY_B)
    assert len(session.client.calls_for("get_network_policy_tag")) == 1
    assert [call.args[0] for call in session.client.calls_for("get_network_policy")] == [POLICY_A, POLICY_A]

    entries, _ = await invoke(session.history)
    selected = entries[-1]
    assert selected.network_policy_uuids == (POLICY_A, POLICY_B)
    stored = await invoke(session.store.get_node, session.session_id, selected.id)
    assert stored.data["network_policy_uuids"] == [POLICY_A, POLICY_B]
    assert selected.image_uuid == entries[0].image_uuid

    await invoke(session.run, "first")
    await invoke(session.change_network_policy, None)
    assert session.client.calls_for("spawn_instance")[0].kwargs["networking"].policy == [POLICY_A, POLICY_B]

    # Rebinding the tag must not alter a saved selection, or be queried on resume.
    session.client.mock("get_network_policy_tag", NetworkPolicyTag(tag="restricted", uuid=POLICY_A))
    await invoke(session.store.close)
    store = type(session.store)(tmp_path / "session.db")
    try:
        restored = type(session)(
            session.client,
            session_id=session.session_id,
            node_id=selected.id,
            store=store,
            network_policy="tag:ignored-on-resume",
        )
        if isinstance(restored, ContreeAsyncSession):
            await restored.ensure_ready()
        assert restored.network_policy_uuids == (POLICY_A, POLICY_B)
        assert len(session.client.calls_for("get_network_policy_tag")) == 1
        assert [call.args[0] for call in session.client.calls_for("get_network_policy")] == [POLICY_A, POLICY_A]
    finally:
        await invoke(store.close)


@pytest.mark.parametrize("selection", [None, [], ()])
async def test_clear_selection_uses_backend_defaults_and_preserves_enabled(session, selection):
    await invoke(session.change_network_policy, selection)
    assert session.network_policy_uuids == ()
    assert session.network_enabled is False
    await invoke(session.run, "first")
    assert session.client.calls_for("spawn_instance")[0].kwargs["networking"].to_dict() == {
        "enabled": False,
        "policy": [],
    }


@pytest.mark.parametrize(
    ("method", "args", "kwargs"),
    [("change_network_policy", (POLICY_B,), {}), ("run", ("first",), {"network_policy": POLICY_B})],
)
async def test_missing_policy_uuid_does_not_change_defaults_or_start_vm(session, monkeypatch, method, args, kwargs):
    def lookup(uuid):
        assert uuid == POLICY_B
        raise LookupError("missing policy")

    async def async_lookup(uuid):
        return lookup(uuid)

    monkeypatch.setattr(
        session.client, "get_network_policy", async_lookup if isinstance(session, ContreeAsyncSession) else lookup
    )
    tip = session.tip_id
    with pytest.raises(LookupError, match="missing policy"):
        await invoke(getattr(session, method), *args, **kwargs)

    assert session.tip_id == tip
    assert session.network_policy_uuids == (POLICY_A,)
    assert session.network_enabled is False
    assert not session.client.calls_for("spawn_instance")


@pytest.mark.parametrize("selection", ["", "tag:", "bare-tag", [POLICY_A, ""], ["tag:restricted", "bad-uuid"]])
async def test_invalid_references_are_rejected_before_lookup_or_history_change(session, selection):
    tip = session.tip_id
    with pytest.raises(ValueError, match="network policy"):
        await invoke(session.change_network_policy, selection)
    assert session.tip_id == tip
    assert session.network_policy_uuids == (POLICY_A,)
    assert not session.client.calls_for("get_network_policy_tag")


@pytest.fixture(params=[False, True], ids=["sync", "async"])
async def lazy_session(request):
    client: LiveAsyncClient | LiveClient
    base: ContreeAsyncSession | ContreeSession
    lazy: AsyncLazySession | LazySession
    if request.param:
        client = LiveAsyncClient()
        client.mock("get_network_policy")
        base = ContreeAsyncSession(client, image="base", network_policy=POLICY_A)
        lazy = AsyncLazySession(base, snapshot_policy=ManualSnapshotPolicy())
    else:
        client = LiveClient()
        client.mock("get_network_policy")
        base = ContreeSession(client, image="base", network_policy=POLICY_A)
        lazy = LazySession(base, snapshot_policy=ManualSnapshotPolicy())
    try:
        yield client, base, lazy
    finally:
        await invoke(lazy.abort)
        await invoke(base.store.close)


@pytest.mark.parametrize("active", [False, True], ids=["cold", "running"])
@pytest.mark.parametrize(
    "overrides",
    [
        {"network_policy": POLICY_A},
        {"network_policy": "tag:temporary"},
        {"network_policy": []},
        {"network_enabled": False},
        {"network_enabled": True},
    ],
)
async def test_lazy_rejects_network_overrides_without_affecting_vm(lazy_session, active, overrides):
    client, base, lazy = lazy_session
    if isinstance(base, ContreeAsyncSession):
        await base.ensure_ready()
    if active:
        await invoke(lazy.run, "first")
    phase = lazy.phase
    tip = base.tip_id
    calls = list(client.calls)

    with pytest.raises(ValueError, match=r"use change_network_policy\(\) or change_network_enabled\(\)"):
        await invoke(lazy.run, "override", **overrides)

    assert client.calls == calls
    assert lazy.phase == phase
    assert base.tip_id == tip
    assert lazy.network_policy_uuids == (POLICY_A,)
    assert lazy.network_enabled is True

    await invoke(lazy.run, "inherited", network_policy=None, network_enabled=None)
    assert len(client.calls_for("spawn_instance")) == 1
    assert client.calls_for("spawn_instance")[0].kwargs["networking"].to_dict() == {
        "enabled": True,
        "policy": [POLICY_A],
    }


async def test_lazy_changes_snapshot_before_next_vm_and_retain_policy(lazy_session):
    client, base, lazy = lazy_session
    await invoke(lazy.run, "first")

    await invoke(lazy.change_network_policy, POLICY_B)
    assert lazy.phase == "cold"
    entries, _ = await invoke(base.history)
    assert [entry.kind for entry in entries] == ["init", "run", "config"]
    saved_data = await entry_data(base, entries[1])
    assert saved_data["network_policy_uuids"] == [POLICY_A]
    saved_data = await entry_data(base, entries[2])
    assert saved_data["network_policy_uuids"] == [POLICY_B]
    assert entries[1].image_uuid == entries[2].image_uuid == "image-op-1"

    await invoke(lazy.run, "third")
    await invoke(lazy.change_network_enabled, False)
    assert lazy.network_policy_uuids == (POLICY_B,)
    await invoke(lazy.run, "fourth")
    await invoke(lazy.change_network_enabled, True)
    await invoke(lazy.run, "fifth")
    await invoke(lazy.change_network_policy, None)
    await invoke(lazy.run, "sixth")
    calls = client.calls_for("spawn_instance")
    assert [call.kwargs["networking"].to_dict() for call in calls] == [
        {"enabled": True, "policy": [POLICY_A]},
        {"enabled": True, "policy": [POLICY_B]},
        {"enabled": False, "policy": [POLICY_B]},
        {"enabled": True, "policy": [POLICY_B]},
        {"enabled": True, "policy": []},
    ]
    assert [call.args[1] for call in calls] == ["base", "image-op-1", "image-op-2", "image-op-3", "image-op-4"]
    assert [call.args[0] for call in client.calls_for("get_network_policy")] == [POLICY_A, POLICY_B]
    await invoke(lazy.close)


async def test_cold_lazy_change_does_not_start_vm(lazy_session):
    client, base, lazy = lazy_session
    await invoke(lazy.change_network_policy, POLICY_B)
    await invoke(lazy.change_network_enabled, False)
    assert not client.calls_for("spawn_instance")
    entries, _ = await invoke(base.history)
    assert [entry.kind for entry in entries] == ["init", "config", "config"]
    await invoke(lazy.run, "first")
    assert client.calls_for("spawn_instance")[0].kwargs["networking"].to_dict() == {
        "enabled": False,
        "policy": [POLICY_B],
    }


async def test_lazy_resolves_multiple_tags_before_snapshot(lazy_session):
    client, base, lazy = lazy_session
    await invoke(lazy.run, "first")
    client.mock("get_network_policy_tag", NetworkPolicyTag(tag="restricted", uuid=POLICY_B))
    await invoke(lazy.change_network_policy, [POLICY_A, "tag:restricted"])
    entries, _ = await invoke(base.history)
    assert [entry.kind for entry in entries] == ["init", "run", "config"]
    saved_data = await entry_data(base, entries[1])
    assert saved_data["network_policy_uuids"] == [POLICY_A]
    saved_data = await entry_data(base, entries[2])
    assert saved_data["network_policy_uuids"] == [POLICY_A, POLICY_B]
    assert lazy.network_policy_uuids == (POLICY_A, POLICY_B)
    calls = [call.operation for call in client.calls]
    assert calls.index("get_network_policy_tag") < calls.index("operation_subprocess_kill")
    assert len(client.calls_for("get_network_policy_tag")) == 1
    await invoke(lazy.run, "second")
    assert client.calls_for("spawn_instance")[1].kwargs["networking"].policy == [POLICY_A, POLICY_B]
    assert [call.args[0] for call in client.calls_for("get_network_policy")] == [POLICY_A, POLICY_A]


@pytest.mark.parametrize(
    ("method", "references"),
    [
        ("get_network_policy_tag", ["tag:valid", "tag:missing"]),
        ("get_network_policy", [POLICY_A, POLICY_B]),
    ],
    ids=["tag", "uuid"],
)
async def test_failed_policy_lookup_keeps_active_vm_and_previous_policies(
    lazy_session, monkeypatch, method, references
):
    client, base, lazy = lazy_session
    await invoke(lazy.run, "first")

    def lookup(reference):
        if reference in {"missing", POLICY_B}:
            raise LookupError("missing policy")
        return NetworkPolicyTag(tag=reference, uuid=POLICY_B) if method == "get_network_policy_tag" else None

    async def async_lookup(reference):
        return lookup(reference)

    monkeypatch.setattr(client, method, async_lookup if isinstance(base, ContreeAsyncSession) else lookup)
    with pytest.raises(LookupError, match="missing policy"):
        await invoke(lazy.change_network_policy, references)
    assert lazy.phase == "running"
    assert lazy.network_policy_uuids == (POLICY_A,)
    assert not client.calls_for("operation_subprocess_kill")
    assert len((await invoke(base.history))[0]) == 1
    await invoke(lazy.run, "still-usable")
    assert len(client.calls_for("spawn_instance")) == 1


async def test_snapshot_failure_does_not_record_requested_network_change(lazy_session):
    client, base, lazy = lazy_session
    await invoke(lazy.run, "first")
    client.wait_error = OSError("snapshot unavailable")
    with pytest.raises(RuntimeError, match="snapshot failed"):
        await invoke(lazy.change_network_policy, POLICY_B)
    assert lazy.network_policy_uuids == (POLICY_A,)
    entries, _ = await invoke(base.history)
    assert [entry.kind for entry in entries] == ["init"]


async def test_invalid_inputs_do_not_stop_active_vm(lazy_session):
    client, base, lazy = lazy_session
    await invoke(lazy.run, "first")
    with pytest.raises(TypeError, match="references must be strings"):
        await invoke(lazy.change_network_policy, [POLICY_A, None])
    with pytest.raises(TypeError, match="bool"):
        await invoke(lazy.change_network_enabled, "false")
    with pytest.raises(TypeError, match="bool"):
        await invoke(lazy.change_network_enabled, None)
    assert lazy.phase == "running"
    assert not client.calls_for("operation_subprocess_kill")
    assert len((await invoke(base.history))[0]) == 1


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
async def test_factory_initializes_lazy_base_networking(asynchronous):
    client = LiveAsyncClient() if asynchronous else LiveClient()
    client.mock("get_network_policy")
    client.mock("get_network_policy_tag", NetworkPolicyTag(tag="restricted", uuid=POLICY_B))
    context = create_sandbox_session(
        image="base", client=client, network_policy=[POLICY_A, "tag:restricted"], network_enabled=False
    )
    if asynchronous:
        async with context as session:
            await session.run("first")
            assert session.network_policy_uuids == (POLICY_A, POLICY_B)
            assert session.network_enabled is False
    else:
        with context as session:
            session.run("first")
            assert session.network_policy_uuids == (POLICY_A, POLICY_B)
            assert session.network_enabled is False
    assert client.calls_for("spawn_instance")[0].kwargs["networking"].to_dict() == {
        "enabled": False,
        "policy": [POLICY_A, POLICY_B],
    }


async def test_async_upload_cannot_change_inflight_network_selection():
    entered = asyncio.Event()
    proceed = asyncio.Event()
    client = ContreeAsyncClient()
    client.mock("get_network_policy")
    client.mock("resolve_image", "base")
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response())

    class GatedTransfer(AsyncClientFileTransfer):
        async def prepare_files(self, files):
            entered.set()
            await proceed.wait()
            return await super().prepare_files(files)

    session = ContreeAsyncSession(client, image="base", network_policy=POLICY_A, file_transfer=GatedTransfer(client))
    spawning = asyncio.create_task(session.spawn("first"))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await session.change_network_policy(POLICY_B)
        await session.change_network_enabled(False)
        proceed.set()
        operation = await asyncio.wait_for(spawning, 2)
        await operation.wait()
        entry = await session.commit_result(operation)
        await operation.shutdown()
        assert entry is not None
        assert client.calls_for("spawn_instance")[0].kwargs["networking"].to_dict() == {
            "enabled": True,
            "policy": [POLICY_A],
        }
        saved_data = await entry_data(session, entry)
        assert saved_data["network_policy_uuids"] == [POLICY_A]
        assert saved_data["network_enabled"] is True
        assert session.network_policy_uuids == (POLICY_B,)
        assert session.network_enabled is False
    finally:
        proceed.set()
        await spawning
        await session.store.close()
