"""Bounded schedules and counterexamples for actors using only the Store contract."""

from dataclasses import replace

import pytest

from contree_sdk.store import AsyncMemoryStore, Node, NodeConflictError, SyncMemoryStore
from tests.unit.store.test_tree_store import call, seed


def schedules(remaining):
    """Enumerate every interleaving, preserving each actor's delivery order."""
    if not any(remaining):
        yield ()
    for actor, count in enumerate(remaining):
        if count:
            rest = (*remaining[:actor], count - 1, *remaining[actor + 1 :])
            for tail in schedules(rest):
                yield (actor, *tail)


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_all_three_actor_delivery_schedules(asynchronous):
    store = AsyncMemoryStore() if asynchronous else SyncMemoryStore()
    try:
        count = 0
        for schedule in schedules((3, 3, 3)):
            root = await seed(store)
            first = [Node(id=f"{actor}:a", parent_id=root.id, kind="run") for actor in range(3)]
            last = [Node(id=f"{actor}:b", parent_id=first[actor].id, kind="run") for actor in range(3)]
            deliveries = [(first[actor], first[actor], last[actor]) for actor in range(3)]
            positions = [0, 0, 0]
            expected = {root.id: root}
            for actor in schedule:
                node = deliveries[actor][positions[actor]]
                positions[actor] += 1
                await call(store.append, "s", node)
                expected[node.id] = node
                # Compare each prefix against a set model, not a shared-head model.
                actual = (await call(store.list_nodes, "s")).items
                assert {item.id: item for item in actual} == expected
            for actor in range(3):
                history = (await call(store.list_history, "s", last[actor].id)).items
                assert history == (last[actor], first[actor], root)
            await call(store.delete_session, "s")
            count += 1
        assert count == 1680
    finally:
        await call(store.close)


async def test_cursor_is_not_an_append_subscription(store_case):
    store = store_case
    await seed(store)
    for identity in ("b", "d"):
        await call(store.append, "s", Node(id=identity, parent_id="root", kind="run"))
    first = await call(store.list_nodes, "s", kind="run", limit=1)
    assert first.items[0].id == "b"
    # Another actor writes both before and after the reader's cursor.
    for identity in ("a", "c"):
        await call(store.append, "s", Node(id=identity, parent_id="root", kind="run"))
    rest = await call(store.list_nodes, "s", kind="run", cursor=first.next_cursor)
    assert [node.id for node in rest.items] == ["c", "d"]
    assert [node.id for node in (await call(store.list_nodes, "s", kind="run")).items] == ["a", "b", "c", "d"]


async def test_fixed_ancestry_stays_complete_while_other_actors_append(store_case):
    store = store_case
    root = await seed(store)
    parent = root
    for identity in ("z", "a", "m"):
        parent = Node(id=identity, parent_id=parent.id, kind="run")
        await call(store.append, "s", parent)
    cursor = None
    seen = []
    for identity in ("other-1", "other-2"):
        page = await call(store.list_history, "s", "m", limit=2, cursor=cursor)
        seen.extend(node.id for node in page.items)
        cursor = page.next_cursor
        await call(store.append, "s", Node(id=identity, parent_id="root", kind="run"))
    assert seen == ["m", "a", "z", "root"]
    assert cursor is None


async def test_conflicting_retries_do_not_rewrite_parent_or_payload(store_case):
    store = store_case
    await seed(store)
    first = Node(id="first", parent_id="root", kind="run", data={"actor": "a"})
    other = Node(id="other", parent_id="root", kind="run")
    await call(store.append, "s", first)
    await call(store.append, "s", other)
    for conflict in (replace(first, parent_id="other"), replace(first, data={"actor": "b"})):
        with pytest.raises(NodeConflictError):
            await call(store.append, "s", conflict)
    assert await call(store.get_node, "s", first.id) == first


async def test_reused_tree_and_parent_ids_do_not_fence_an_old_writer(store_case):
    store = store_case
    root = await seed(store)
    delayed = Node(id="old-result", parent_id=root.id, kind="run")
    await call(store.delete_session, "s")
    with pytest.raises(ValueError):
        await call(store.append, "s", delayed)
    await call(store.create_session, "s")
    # A fresh root identity rejects the old writer even if the session ID is reused.
    await call(store.append, "s", Node(id="new-root", parent_id=None, kind="init"))
    with pytest.raises(ValueError):
        await call(store.append, "s", delayed)
    await call(store.delete_session, "s")
    await seed(store)
    # Reusing BOTH identities removes that distinction. There is no lifetime token.
    await call(store.append, "s", delayed)
    assert await call(store.get_node, "s", delayed.id) == delayed
