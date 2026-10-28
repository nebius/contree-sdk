from collections.abc import Iterable

from contree_sdk.store import AsyncSQLiteStore, AsyncStore, Node, SyncSQLiteStore, SyncStore
from contree_sdk.store.tree import encode_data


async def seed_nodes(store: SyncStore | AsyncStore, session_id: str, nodes: Iterable[Node]) -> None:
    """Populate read-test fixtures with one SQLite transaction."""
    if isinstance(store, (SyncSQLiteStore, AsyncSQLiteStore)):
        rows = [(session_id, node.id, node.parent_id, node.kind, encode_data(node.data)) for node in nodes]
        sql = "INSERT INTO tree_nodes (session_id,id,parent,kind,data) VALUES (?,?,?,?,?)"
        if isinstance(store, SyncSQLiteStore):
            with store._transaction(write=True):
                store.conn.executemany(sql, rows).close()
        else:
            async with store._transaction(write=True):
                if store.conn is None:
                    raise RuntimeError("store is not connected")
                async with store.conn.executemany(sql, rows):
                    pass
        return
    for node in nodes:
        if isinstance(store, AsyncStore):
            await store.append(session_id, node)
        else:
            store.append(session_id, node)
