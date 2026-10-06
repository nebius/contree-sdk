"""Store reads remain bounded and preserve their contract across connections."""

import base64
import json

import pytest

from contree_sdk.store import AsyncSQLiteStore, Node, SyncSQLiteStore
from tests.unit.store.test_tree_store import call, seed


async def test_batch_preserves_order_missing_slots_and_independent_json(store_case):
    store = store_case
    root = await seed(store)
    node = Node(id="a", parent_id=root.id, kind="run", data={"nested": [1]})
    await call(store.append, "s", node)
    batch = await call(store.get_nodes, "s", ("a", "missing", "root", "a"))
    assert batch == (node, None, root, node)
    batch[0].data["nested"].append(2)
    assert batch[3].data == {"nested": [1]}
    assert (await call(store.get_node, "s", "a")).data == {"nested": [1]}
    assert await call(store.get_nodes, "s", ()) == ()
    assert len(await call(store.get_nodes, "s", ("root",) * 1000)) == 1000
    with pytest.raises(ValueError, match="1000"):
        await call(store.get_nodes, "s", ("root",) * 1001)
    with pytest.raises(ValueError):
        await call(store.get_nodes, "s", ("",))
    await call(store.set_session_ttl, "s", 0)
    for ids in [(), ("root",)]:
        with pytest.raises(ValueError, match="expired"):
            await call(store.get_nodes, "s", ids)


@pytest.mark.parametrize("factory", [SyncSQLiteStore, AsyncSQLiteStore])
async def test_history_continues_after_reopen_with_page_bounded_work(factory, tmp_path):
    path = tmp_path / "history.db"
    store = factory(path)
    await seed(store)
    parent = "root"
    for index in range(1100):
        node = Node(id=f"step-{index:04}", parent_id=parent, kind="run")
        await call(store.append, "s", node)
        parent = node.id
    first = await call(store.list_history, "s", parent)
    assert len(first.items) == 1000
    token = first.next_cursor
    await call(store.close)

    store = factory(path)
    try:
        await call(store.get_session, "s")  # Open the async connection before measuring.
        work = []

        def progress():
            work.append(1)
            return 0

        await call(store.conn.set_progress_handler, progress, 10)
        near_tip = await call(store.list_history, "s", parent, limit=10)
        first_work = len(work)
        work.clear()
        far_from_tip = await call(store.list_history, "s", parent, limit=10, cursor=token)
        assert len(work) <= first_work * 2
        assert [node.id for node in near_tip.items] == [f"step-{index:04}" for index in range(1099, 1089, -1)]
        assert [node.id for node in far_from_tip.items] == [f"step-{index:04}" for index in range(99, 89, -1)]
        await call(store.conn.set_progress_handler, None, 0)
        remainder = await call(store.list_history, "s", parent, cursor=token)
        assert len(remainder.items) == 101
        assert remainder.items[-1].id == "root"
        assert remainder.next_cursor is None
        with pytest.raises(ValueError, match="selection"):
            await call(store.list_history, "s", "root", cursor=token)
        with pytest.raises(ValueError):
            await call(store.list_history, "s", parent, cursor="not-a-cursor")
        unknown = base64.urlsafe_b64encode(
            json.dumps({"scope": ["history", "s", parent], "position": "missing"}).encode()
        ).decode()
        with pytest.raises(ValueError, match="unknown node"):
            await call(store.list_history, "s", parent, cursor=unknown)
        await call(store.delete_session, "s")
        with pytest.raises(ValueError, match="expired"):
            await call(store.list_history, "s", parent, cursor=token)
    finally:
        await call(store.close)


@pytest.mark.parametrize("factory", [SyncSQLiteStore, AsyncSQLiteStore])
async def test_batch_over_sqlite_parameter_boundary(factory, tmp_path):
    store = factory(tmp_path / "batch.db")
    try:
        await seed(store)
        ids = tuple(f"node-{index}" for index in range(1000))
        for node_id in ids:
            await call(store.append, "s", Node(id=node_id, parent_id="root", kind="run"))
        batch = await call(store.get_nodes, "s", tuple(reversed(ids)))
        assert [node.id for node in batch] == list(reversed(ids))
    finally:
        await call(store.close)
