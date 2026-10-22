import pytest

from contree_sdk.store import AsyncMemoryStore, AsyncSQLiteStore, Node, SyncMemoryStore, SyncSQLiteStore
from tests.unit.store.test_tree_store import call


@pytest.mark.parametrize("factory", [SyncMemoryStore, AsyncMemoryStore, SyncSQLiteStore, AsyncSQLiteStore])
async def test_retention_is_explicit_and_does_not_renew_on_read_or_retry(factory, tmp_path):
    now = [10.0]
    kwargs = {"clock": lambda: now[0]}
    store = factory(tmp_path / "ttl.db", **kwargs) if "SQLite" in factory.__name__ else factory(**kwargs)
    try:
        info = await call(store.create_session, "s", ttl=10)
        node = Node(id="root", parent_id=None, kind="init")
        await call(store.append, "s", node)
        now[0] = 15
        assert await call(store.create_session, "s", ttl=100) == info
        await call(store.append, "s", node)
        assert (await call(store.get_session, "s")).expires_at == 20
        now[0] = 20
        assert await call(store.get_session, "s") is None
        assert not (await call(store.list_sessions)).items
        with pytest.raises(ValueError):
            await call(store.append, "s", node)
        with pytest.raises(ValueError):
            await call(store.get_node, "s", "root")
        await call(store.create_session, "s", ttl=None)
        assert (await call(store.get_session, "s")).expires_at is None
        assert not (await call(store.list_nodes, "s")).items
        await call(store.set_session_ttl, "s", 5)
        now[0] = 25
        assert await call(store.get_session, "s") is None
    finally:
        await call(store.close)
