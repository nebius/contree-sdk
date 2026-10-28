"""Volatile tree stores. SQLite's memory engine enforces the same invariants."""

from __future__ import annotations

import time

from contree_sdk.store.base import AsyncStore, SyncStore
from contree_sdk.store.sqlite import SyncSQLiteStore
from contree_sdk.store.tree import DEFAULT_PAGE_SIZE, Node, NodeId, Page, SessionInfo
from contree_sdk.store.ttl import Clock


class SyncMemoryStore(SyncStore):
    def __init__(self, *, clock: Clock = time.time) -> None:
        self.memory = SyncSQLiteStore(":memory:", clock=clock)

    def create_session(self, session_id: str, *, kind: str = "session", ttl: float | None = None) -> SessionInfo:
        return self.memory.create_session(session_id, kind=kind, ttl=ttl)

    def get_session(self, session_id: str) -> SessionInfo | None:
        return self.memory.get_session(session_id)

    def set_session_ttl(self, session_id: str, ttl: float | None) -> SessionInfo:
        return self.memory.set_session_ttl(session_id, ttl)

    def delete_session(self, session_id: str) -> bool:
        return self.memory.delete_session(session_id)

    def list_sessions(
        self, *, kind: str | None = None, prefix: str = "", limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[SessionInfo]:
        return self.memory.list_sessions(kind=kind, prefix=prefix, limit=limit, cursor=cursor)

    def append(self, session_id: str, node: Node) -> None:
        return self.memory.append(session_id, node)

    def get_node(self, session_id: str, node_id: NodeId) -> Node:
        return self.memory.get_node(session_id, node_id)

    def get_nodes(self, session_id: str, node_ids: tuple[NodeId, ...]) -> tuple[Node | None, ...]:
        return self.memory.get_nodes(session_id, node_ids)

    def list_nodes(
        self, session_id: str, *, kind: str | None = None, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Node]:
        return self.memory.list_nodes(session_id, kind=kind, limit=limit, cursor=cursor)

    def list_children(
        self,
        session_id: str,
        parent_id: NodeId | None,
        *,
        kind: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[Node]:
        return self.memory.list_children(session_id, parent_id, kind=kind, limit=limit, cursor=cursor)

    def list_history(
        self, session_id: str, from_node: NodeId, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Node]:
        return self.memory.list_history(session_id, from_node, limit=limit, cursor=cursor)

    def close(self) -> None:
        return self.memory.close()


class AsyncMemoryStore(AsyncStore):
    def __init__(self, *, clock: Clock = time.time) -> None:
        self.memory = SyncMemoryStore(clock=clock)

    async def create_session(self, session_id: str, *, kind: str = "session", ttl: float | None = None) -> SessionInfo:
        return self.memory.create_session(session_id, kind=kind, ttl=ttl)

    async def get_session(self, session_id: str) -> SessionInfo | None:
        return self.memory.get_session(session_id)

    async def set_session_ttl(self, session_id: str, ttl: float | None) -> SessionInfo:
        return self.memory.set_session_ttl(session_id, ttl)

    async def delete_session(self, session_id: str) -> bool:
        return self.memory.delete_session(session_id)

    async def list_sessions(
        self, *, kind: str | None = None, prefix: str = "", limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[SessionInfo]:
        return self.memory.list_sessions(kind=kind, prefix=prefix, limit=limit, cursor=cursor)

    async def append(self, session_id: str, node: Node) -> None:
        return self.memory.append(session_id, node)

    async def get_node(self, session_id: str, node_id: NodeId) -> Node:
        return self.memory.get_node(session_id, node_id)

    async def get_nodes(self, session_id: str, node_ids: tuple[NodeId, ...]) -> tuple[Node | None, ...]:
        return self.memory.get_nodes(session_id, node_ids)

    async def list_nodes(
        self, session_id: str, *, kind: str | None = None, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Node]:
        return self.memory.list_nodes(session_id, kind=kind, limit=limit, cursor=cursor)

    async def list_children(
        self,
        session_id: str,
        parent_id: NodeId | None,
        *,
        kind: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[Node]:
        return self.memory.list_children(session_id, parent_id, kind=kind, limit=limit, cursor=cursor)

    async def list_history(
        self, session_id: str, from_node: NodeId, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Node]:
        return self.memory.list_history(session_id, from_node, limit=limit, cursor=cursor)

    async def close(self) -> None:
        return self.memory.close()
