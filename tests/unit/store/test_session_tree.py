import pytest
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk import ContreeAsyncSession, ContreeSession
from contree_sdk.store import AsyncStore
from tests.unit.session.factories import mock_completion, operation_response, spawn_response
from tests.unit.store.test_tree_store import call


def client_for(store, name):
    client = ContreeAsyncClient() if isinstance(store, AsyncStore) else ContreeClient()
    client.mock("resolve_image", "base")
    client.mock("spawn_instance", spawn_response(name))
    mock_completion(client, operation_response(operation_uuid=name, result_image_uuid="image-" + name))
    return client


async def session_for(store, client, **kwargs):
    cls = ContreeAsyncSession if isinstance(store, AsyncStore) else ContreeSession
    session = cls(client, store=store, session_id="shared", **kwargs)
    if isinstance(session, ContreeAsyncSession):
        await session.ensure_ready()
    return session


async def test_two_actors_keep_independent_positions_and_resume_requires_choice(store_case):
    store = store_case
    a = await session_for(store, client_for(store, "a"), image="base")
    root = a.tip_id
    b = await session_for(store, client_for(store, "b"), node_id=root)
    await call(a.create_branch, "local")
    await call(a.switch_branch, "local")
    assert await call(b.list_branches) == [("main", True)]
    await call(a.run, "first")
    await call(b.run, "second")
    assert a.image_uuid == "image-a"
    assert b.image_uuid == "image-b"
    children = (await call(store.list_children, "shared", root)).items
    assert {node.id for node in children} == {a.tip_id, b.tip_id}
    assert all(node.parent_id == root for node in children)
    with pytest.raises(ValueError, match="node_id"):
        await session_for(store, client_for(store, "resume"))
    resumed = await session_for(store, client_for(store, "resume"), node_id=b.tip_id)
    assert resumed.image_uuid == b.image_uuid
    await call(a.rollback)
    assert a.tip_id == root
    assert b.image_uuid == "image-b"
    with pytest.raises(ValueError, match="continuation"):
        await call(a.navigate_forward)


async def test_late_result_and_retry_do_not_undo_local_navigation(store_case):
    store = store_case
    session = await session_for(store, client_for(store, "late"), image="base")
    operation = await call(session.spawn, "work")
    root = session.tip_id
    await call(session.create_branch, "other")
    await call(session.switch_branch, "other")
    await call(session.switch_branch, "main")
    await call(operation.wait)
    entry = await call(session.commit_result, operation)
    assert entry.parent_id == root
    assert session.tip_id == root
    assert await call(session.commit_result, operation) == entry
    assert len((await call(store.list_children, "shared", root)).items) == 1
    assert session.tip_id == root


async def test_configuration_is_a_local_continuation(store_case):
    store = store_case
    a = await session_for(store, client_for(store, "a"), image="base")
    b = await session_for(store, client_for(store, "b"), node_id=a.tip_id)
    await call(a.set_env, {"SIDE": "a"})
    await call(b.set_env, {"SIDE": "b"})
    assert a.env == {"SIDE": "a"}
    assert b.env == {"SIDE": "b"}
    assert (await call(store.get_node, "shared", a.tip_id)).data["env"] == {"SIDE": "a"}
    assert (await call(store.get_node, "shared", b.tip_id)).data["env"] == {"SIDE": "b"}
