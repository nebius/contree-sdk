"""Real VM interface checks against an explicitly selected test profile."""

import inspect
import os
from uuid import uuid4

import pytest
from contree_client.asyncio import ContreeAsyncClient
from contree_client.models import (
    InstanceNetworkingResponse,
    InstanceResultState,
    NetworkPolicyCIDRRule,
    OperationInstanceMetadata,
    StreamRepr,
)
from contree_client.sync import ContreeClient

from contree_sdk import ContreeAsyncSession, ContreeSession, create_sandbox_session
from contree_sdk.store import AsyncSQLiteStore, SyncSQLiteStore


@pytest.fixture
def network_image():
    image = os.getenv("CONTREE_E2E_IMAGE")
    if not image or not os.getenv("CONTREE_PROFILE"):
        pytest.skip("Set CONTREE_PROFILE to a test deployment and CONTREE_E2E_IMAGE to an Alpine image")
    return image


@pytest.mark.parametrize("lazy", [False, True], ids=["regular", "lazy"])
def test_network_interface_changes_with_session_flag(network_image, lazy):
    with (
        ContreeClient.from_profile(timeout=30, retry=None) as client,
        create_sandbox_session(
            client=client,
            image=network_image,
            session_type=None if lazy else ContreeSession,
            network_enabled=True,
            session_kwargs={"vm_timeout": 120} if lazy else {},
        ) as session,
    ):
        enabled = session.run("ls", args=("/sys/class/net",), timeout=20)
        assert isinstance(enabled.state, InstanceResultState)
        assert enabled.state.exit_code == 0
        assert isinstance(enabled.stdout, StreamRepr)
        assert set(enabled.stdout.as_text().split()) - {"lo"}

        session.change_network_enabled(False)
        disabled = session.run("ls", args=("/sys/class/net",), timeout=20)
        assert isinstance(disabled.state, InstanceResultState)
        assert disabled.state.exit_code == 0
        assert isinstance(disabled.stdout, StreamRepr)
        assert disabled.stdout.as_text().split() == ["lo"]

        session.change_network_enabled(True)
        restored = session.run("ls", args=("/sys/class/net",), timeout=20)
        assert isinstance(restored.state, InstanceResultState)
        assert restored.state.exit_code == 0
        assert isinstance(restored.stdout, StreamRepr)
        assert set(restored.stdout.as_text().split()) - {"lo"}


@pytest.mark.parametrize("lazy", [False, True], ids=["regular", "lazy"])
async def test_async_network_interface_changes_with_session_flag(network_image, lazy):
    async with (
        ContreeAsyncClient.from_profile(timeout=30, retry=None) as client,
        create_sandbox_session(
            client=client,
            image=network_image,
            session_type=None if lazy else ContreeAsyncSession,
            network_enabled=True,
            session_kwargs={"vm_timeout": 120} if lazy else {},
        ) as session,
    ):
        enabled = await session.run("ls", args=("/sys/class/net",), timeout=20)
        assert isinstance(enabled.state, InstanceResultState)
        assert enabled.state.exit_code == 0
        assert isinstance(enabled.stdout, StreamRepr)
        assert set(enabled.stdout.as_text().split()) - {"lo"}

        await session.change_network_enabled(False)
        disabled = await session.run("ls", args=("/sys/class/net",), timeout=20)
        assert isinstance(disabled.state, InstanceResultState)
        assert disabled.state.exit_code == 0
        assert isinstance(disabled.stdout, StreamRepr)
        assert disabled.stdout.as_text().split() == ["lo"]

        await session.change_network_enabled(True)
        restored = await session.run("ls", args=("/sys/class/net",), timeout=20)
        assert isinstance(restored.state, InstanceResultState)
        assert restored.state.exit_code == 0
        assert isinstance(restored.stdout, StreamRepr)
        assert set(restored.stdout.as_text().split()) - {"lo"}


async def invoke(function, *args, **kwargs):
    result = function(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


async def entry_data(session, entry):
    node = await invoke(session.store.get_node, session.session_id, entry.id)
    return node.data


@pytest.fixture(params=[False, True], ids=["sync", "async"])
async def network_client(request, network_image):
    client = (ContreeAsyncClient if request.param else ContreeClient).from_profile(timeout=30, retry=None)
    await invoke(client.open)
    try:
        yield request.param, client
    finally:
        await invoke(client.close)


@pytest.fixture
async def deny_policy(network_client):
    _, client = network_client
    # Policies are content-addressed. Preserve an existing policy if creation
    # returns one that another test or user already owns.
    existing = set()
    offset = 0
    while True:
        page = await invoke(client.list_network_policies, limit=100, offset=offset)
        existing.update(item.uuid for item in page.policies)
        if len(page.policies) < 100:
            break
        offset += len(page.policies)
    policy = await invoke(client.create_network_policy, [])
    try:
        yield policy
    finally:
        if policy.uuid not in existing:
            await invoke(client.delete_network_policy, policy.uuid)


@pytest.fixture
async def tagged_policy(network_client):
    _, client = network_client
    existing = set()
    offset = 0
    while True:
        page = await invoke(client.list_network_policies, limit=100, offset=offset)
        existing.update(item.uuid for item in page.policies)
        if len(page.policies) < 100:
            break
        offset += len(page.policies)
    policy = await invoke(client.create_network_policy, [NetworkPolicyCIDRRule(cidr="192.0.2.0/24", proto="tcp")])
    tag = f"sdk-e2e-{uuid4().hex}"
    try:
        await invoke(client.set_network_policy_tag, tag, policy.uuid)
        try:
            yield tag, policy
        finally:
            await invoke(client.delete_network_policy_tag, tag)
    finally:
        if policy.uuid not in existing:
            await invoke(client.delete_network_policy, policy.uuid)


@pytest.fixture(params=[False, True], ids=["regular", "lazy"])
async def network_session(request, network_client, network_image, tmp_path):
    asynchronous, client = network_client
    if asynchronous:
        async with (
            AsyncSQLiteStore(tmp_path / "network.db") as store,
            create_sandbox_session(
                client=client,
                store=store,
                image=network_image,
                session_id="network-test",
                session_type=None if request.param else ContreeAsyncSession,
                session_kwargs={"vm_timeout": 120} if request.param else {},
            ) as session,
        ):
            yield request.param, client, session
    else:
        with (
            SyncSQLiteStore(tmp_path / "network.db") as store,
            create_sandbox_session(
                client=client,
                store=store,
                image=network_image,
                session_id="network-test",
                session_type=None if request.param else ContreeSession,
                session_kwargs={"vm_timeout": 120} if request.param else {},
            ) as session,
        ):
            yield request.param, client, session


async def ping(session, **kwargs):
    # A numeric destination avoids confusing DNS failures with policy enforcement.
    result = await invoke(session.run, "ping", args=("-c", "1", "-W", "2", "1.1.1.1"), timeout=10, **kwargs)
    assert isinstance(result.state, InstanceResultState)
    assert isinstance(result.state.exit_code, int)
    return result.state.exit_code


async def test_regular_operation_overrides_leave_session_defaults_unchanged(network_client, network_image, deny_policy):
    asynchronous, client = network_client
    base_type = ContreeAsyncSession if asynchronous else ContreeSession
    session = base_type(client, image=network_image, network_policy=deny_policy.uuid)
    try:
        assert await ping(session) != 0
        assert await ping(session, network_policy=[]) == 0
        assert session.network_policy_uuids == (deny_policy.uuid,)
        entries, _ = await invoke(session.history)
        saved_data = await entry_data(session, entries[-1])
        assert saved_data["network_policy_uuids"] == [deny_policy.uuid]

        disabled = await invoke(session.run, "ls", args=("/sys/class/net",), network_enabled=False, timeout=10)
        assert isinstance(disabled.stdout, StreamRepr)
        assert disabled.stdout.as_text().split() == ["lo"]
        assert session.network_enabled is True
        enabled = await invoke(session.run, "ls", args=("/sys/class/net",), network_enabled=None, timeout=10)
        assert isinstance(enabled.stdout, StreamRepr)
        assert set(enabled.stdout.as_text().split()) - {"lo"}
        assert await ping(session, network_policy=None) != 0
    finally:
        await invoke(session.store.close)


@pytest.mark.parametrize("clear_selection", [None, []], ids=["none", "empty-list"])
async def test_policy_changes_reach_vm_and_operation_metadata(network_session, deny_policy, clear_selection):
    lazy, client, session = network_session
    assert await ping(session) == 0
    await invoke(session.change_network_policy, deny_policy.uuid)
    assert await ping(session) != 0
    if lazy:
        await invoke(session.snapshot)
    base = session.session if lazy else session
    entries, _ = await invoke(base.history)
    policy_run = entries[-1]
    assert policy_run.kind == "run"
    saved_data = await entry_data(base, policy_run)
    assert saved_data["network_policy_uuids"] == [deny_policy.uuid]
    assert policy_run.operation_uuid is not None
    operation = await invoke(client.get_operation_status, policy_run.operation_uuid)
    assert isinstance(operation.metadata, OperationInstanceMetadata)
    assert isinstance(operation.metadata.networking, InstanceNetworkingResponse)
    assert operation.metadata.networking.policy == [deny_policy.uuid]

    await invoke(session.change_network_enabled, False)
    disabled = await invoke(session.run, "ls", args=("/sys/class/net",), timeout=10)
    assert isinstance(disabled.stdout, StreamRepr)
    assert disabled.stdout.as_text().split() == ["lo"]
    await invoke(session.change_network_enabled, True)
    assert session.network_policy_uuids == (deny_policy.uuid,)
    assert await ping(session) != 0

    await invoke(session.change_network_policy, clear_selection)
    assert await ping(session) == 0


async def test_mixed_policy_references_are_pinned_before_vm_creation(network_session, deny_policy, tagged_policy):
    lazy, client, session = network_session
    tag, policy = tagged_policy
    await invoke(session.change_network_policy, [deny_policy.uuid, f"tag:{tag}"])
    assert session.network_policy_uuids == (deny_policy.uuid, policy.uuid)

    # Changing the tag before VM creation must not change the saved selection.
    await invoke(client.set_network_policy_tag, tag, deny_policy.uuid)
    result = await invoke(session.run, "true", timeout=10)
    assert isinstance(result.state, InstanceResultState)
    assert result.state.exit_code == 0
    if lazy:
        await invoke(session.snapshot)
    base = session.session if lazy else session
    entries, _ = await invoke(base.history)
    saved = entries[-1]
    saved_data = await entry_data(base, saved)
    assert saved_data["network_policy_uuids"] == [deny_policy.uuid, policy.uuid]
    assert saved.operation_uuid is not None
    operation = await invoke(client.get_operation_status, saved.operation_uuid)
    assert isinstance(operation.metadata, OperationInstanceMetadata)
    assert isinstance(operation.metadata.networking, InstanceNetworkingResponse)
    assert operation.metadata.networking.policy == [deny_policy.uuid, policy.uuid]

    await invoke(session.change_network_policy, f"tag:{tag}")
    assert session.network_policy_uuids == (deny_policy.uuid,)


async def test_selected_policy_is_enforced_after_store_reopen(network_session, network_client, deny_policy, tmp_path):
    lazy, client, session = network_session
    await invoke(session.change_network_policy, deny_policy.uuid)
    assert await ping(session) != 0
    if lazy:
        await invoke(session.snapshot)
    base = session.session if lazy else session
    entries, _ = await invoke(base.history)
    selected = entries[-1]
    # Select the saved node explicitly: the first session still has its own position.
    if network_client[0]:
        async with AsyncSQLiteStore(tmp_path / "network.db") as store:
            resumed = ContreeAsyncSession(client, session_id="network-test", node_id=selected.id, store=store)
            await resumed.ensure_ready()
            assert resumed.network_policy_uuids == (deny_policy.uuid,)
            assert await ping(resumed) != 0
            assert await ping(resumed, network_policy=[]) == 0
    else:
        with SyncSQLiteStore(tmp_path / "network.db") as store:
            resumed = ContreeSession(client, session_id="network-test", node_id=selected.id, store=store)
            assert resumed.network_policy_uuids == (deny_policy.uuid,)
            assert await ping(resumed) != 0
            assert await ping(resumed, network_policy=[]) == 0
