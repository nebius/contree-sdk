import asyncio
import inspect
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from typing import Any

import pytest

from contree_sdk.store import AsyncSQLiteStore, JSONValue, Node, NodeConflictError, SyncSQLiteStore


async def call(method, *args, **kwargs):
    result = method(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


async def seed(store):
    await call(store.create_session, "s", kind="session")
    root = Node(id="root", parent_id=None, kind="init", data={"image_uuid": "image"})
    await call(store.append, "s", root)
    return root


async def test_siblings_and_retry_preserve_both_results(store_case):
    store = store_case
    root = await seed(store)
    a = Node(id="a", parent_id=root.id, kind="run", data={"user": {"hash": "same"}})
    b = replace(a, id="b")
    for node in (b, a, b, a):
        await call(store.append, "s", node)
    children = await call(store.list_children, "s", root.id)
    assert children.items == (a, b)
    with pytest.raises(NodeConflictError):
        await call(store.append, "s", replace(a, data={"different": True}))
    assert await call(store.get_node, "s", "a") == a


async def test_root_parent_and_lifecycle_invariants(store_case):
    store = store_case
    with pytest.raises(ValueError):
        await call(store.append, "s", Node(id="root", parent_id=None, kind="init"))
    await seed(store)
    with pytest.raises(NodeConflictError):
        await call(store.append, "s", Node(parent_id=None, kind="init"))
    await call(store.create_session, "other")
    await call(store.append, "other", Node(id="foreign", parent_id=None, kind="init"))
    with pytest.raises(ValueError):
        await call(store.append, "s", Node(parent_id="foreign", kind="run"))
    child = Node(parent_id="root", kind="run")
    await call(store.append, "s", child)
    assert await call(store.delete_session, "s") is True
    assert await call(store.delete_session, "s") is False
    with pytest.raises(ValueError):
        await call(store.append, "s", child)
    assert await call(store.get_session, "s") is None


async def test_json_reads_and_writes_are_detached(store_case):
    store = store_case
    await seed(store)
    source_items: list[JSONValue] = [1, {"x": True}]
    payload: dict[str, JSONValue] = {"nested": {"items": source_items}}
    node = Node(id="child", parent_id="root", kind="run", data=payload)
    source_items.append(2)
    await call(store.append, "s", node)
    nested = node.data["nested"]
    assert isinstance(nested, dict)
    items = nested["items"]
    assert isinstance(items, list)
    items.append(3)
    loaded = await call(store.get_node, "s", "child")
    assert loaded.data == {"nested": {"items": [1, {"x": True}]}}
    loaded.data.clear()
    assert (await call(store.get_node, "s", "child")).data
    page = await call(store.list_nodes, "s", kind="run")
    page.items[0].data.clear()
    assert (await call(store.get_node, "s", "child")).data


@pytest.mark.parametrize("data", [{"bad": float("nan")}, {"bad": object()}, {1: "not a JSON key"}])
def test_node_rejects_non_json(data):
    with pytest.raises((ValueError, TypeError)):
        Node(parent_id=None, kind="init", data=data)


async def test_kind_filter_before_pagination_and_cursor_scope(store_case):
    store = store_case
    for name, kind in [("a", "upload-cache"), ("b", "session"), ("c", "docker-build"), ("d", "session")]:
        await call(store.create_session, name, kind=kind)
    first = await call(store.list_sessions, kind="session", limit=1)
    assert [item.session_id for item in first.items] == ["b"]
    assert first.next_cursor is not None
    second = await call(store.list_sessions, kind="session", limit=1, cursor=first.next_cursor)
    assert [item.session_id for item in second.items] == ["d"]
    assert second.next_cursor is None
    with pytest.raises(ValueError):
        await call(store.list_sessions, kind="docker-build", cursor=first.next_cursor)
    with pytest.raises(ValueError):
        await call(store.create_session, "b", kind="docker-build")
    assert (await call(store.list_sessions, prefix="d")).items[0].session_id == "d"


async def test_node_pages_and_ancestry_follow_parents_not_ids(store_case):
    store = store_case
    await seed(store)
    for node in [
        Node(id="z", parent_id="root", kind="run"),
        Node(id="a", parent_id="z", kind="run"),
        Node(id="b", parent_id="root", kind="stage"),
    ]:
        await call(store.append, "s", node)
    first = await call(store.list_nodes, "s", kind="run", limit=1)
    assert first.items[0].id == "a"
    second = await call(store.list_nodes, "s", kind="run", limit=1, cursor=first.next_cursor)
    assert second.items[0].id == "z"
    first = await call(store.list_history, "s", "a", limit=1)
    assert [node.id for node in first.items] == ["a"]
    second = await call(store.list_history, "s", "a", limit=2, cursor=first.next_cursor)
    assert [node.id for node in second.items] == ["z", "root"]
    assert second.next_cursor is None
    with pytest.raises(ValueError):
        await call(store.list_history, "s", "b", cursor=first.next_cursor)
    children = await call(store.list_children, "s", "root", kind="stage", limit=1)
    assert [node.id for node in children.items] == ["b"]
    assert children.next_cursor is None


@pytest.mark.parametrize("ttl", [-1, float("inf"), float("nan")])
async def test_invalid_ttl_has_no_side_effects(store_case, ttl):
    with pytest.raises(ValueError):
        await call(store_case.create_session, "bad", ttl=ttl)
    assert await call(store_case.get_session, "bad") is None


def test_two_sqlite_connections_append_and_retry(tmp_path):
    path = tmp_path / "shared.db"
    with SyncSQLiteStore(path) as first, SyncSQLiteStore(path) as second:
        first.create_session("s")
        first.append("s", Node(id="root", parent_id=None, kind="init"))
        barrier = Barrier(2)

        def append(store, node_id):
            node = Node(id=node_id, parent_id="root", kind="run")
            barrier.wait()
            store.append("s", node)
            return node

        with ThreadPoolExecutor(2) as pool:
            a = pool.submit(append, first, "a")
            b = pool.submit(append, second, "b")
            a_node, b_node = a.result(), b.result()
        second.append("s", a_node)
        first.append("s", b_node)
        assert [node.id for node in first.list_children("s", "root").items] == ["a", "b"]


async def test_two_async_sqlite_connections_append_and_retry(tmp_path):
    path = tmp_path / "shared.db"
    async with AsyncSQLiteStore(path) as first, AsyncSQLiteStore(path) as second:
        await first.create_session("s")
        await first.append("s", Node(id="root", parent_id=None, kind="init"))
        a = Node(id="a", parent_id="root", kind="run")
        b = Node(id="b", parent_id="root", kind="run")
        await asyncio.gather(first.append("s", a), second.append("s", b))
        await asyncio.gather(second.append("s", a), first.append("s", b))
        assert (await first.list_children("s", "root")).items == (a, b)


async def test_async_cancellation_rolls_back_and_connection_remains_usable(tmp_path, monkeypatch):
    async with AsyncSQLiteStore(tmp_path / "cancel.db") as store:
        await seed(store)
        written = asyncio.Event()
        write = store._write

        async def interrupted(sql, args=()):
            await write(sql, args)
            if sql.startswith("INSERT INTO tree_nodes"):
                written.set()
                await asyncio.Event().wait()

        monkeypatch.setattr(store, "_write", interrupted)
        task = asyncio.create_task(store.append("s", Node(id="cancelled", parent_id="root", kind="run")))
        await written.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        monkeypatch.setattr(store, "_write", write)
        assert not (await store.list_children("s", "root")).items
        await store.append("s", Node(id="next", parent_id="root", kind="run"))
        assert (await store.get_node("s", "next")).parent_id == "root"


@pytest.mark.parametrize(
    "fields", [{"id": 1}, {"id": ""}, {"kind": 1}, {"kind": ""}, {"parent_id": 1}, {"parent_id": ""}]
)
def test_node_rejects_invalid_identity_and_kind(fields):
    values: dict[str, Any] = {"parent_id": None, "kind": "init", **fields}
    with pytest.raises(ValueError):
        Node(**values)


@pytest.mark.parametrize(("session_id", "kind"), [(1, "session"), ("", "session"), ("s", 1), ("s", "")])
async def test_tree_rejects_invalid_identity_and_kind(store_case, session_id, kind):
    with pytest.raises(ValueError):
        await call(store_case.create_session, session_id, kind=kind)
    assert not (await call(store_case.list_sessions)).items
