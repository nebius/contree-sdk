"""Domain store for immutable trees; execution position belongs to Session."""

from __future__ import annotations

from abc import ABC, abstractmethod

from contree_sdk.compat import Self
from contree_sdk.store.tree import DEFAULT_PAGE_SIZE, Node, NodeId, Page, SessionInfo


class SyncStore(ABC):
    """Store independent trees with atomic, idempotent node insertion.

    Repeating create_session with the same kind returns the existing tree without
    renewing TTL. append requires a live tree and an existing parent, except for
    its single root. Repeating an identical node succeeds; changed data conflicts.
    Reads return detached JSON. Node IDs are identities, not execution order.
    Pages use stable identity order; they are live reads, not a shared snapshot.
    None TTL delegates retention to the implementation.

    Calls are atomic across clients sharing a backend. Once a write succeeds,
    subsequent reads through any client observe it unless the tree was deleted
    or expired. Concurrent calls may take either order; separate calls do not
    form a transaction. A lost response does not imply that the write failed.
    Retry append with the same node identity, parent, kind, and data.
    """

    @abstractmethod
    def create_session(self, session_id: str, *, kind: str = "session", ttl: float | None = None) -> SessionInfo: ...

    @abstractmethod
    def get_session(self, session_id: str) -> SessionInfo | None: ...

    @abstractmethod
    def set_session_ttl(self, session_id: str, ttl: float | None) -> SessionInfo: ...

    @abstractmethod
    def delete_session(self, session_id: str) -> bool: ...

    @abstractmethod
    def list_sessions(
        self, *, kind: str | None = None, prefix: str = "", limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[SessionInfo]: ...

    @abstractmethod
    def append(self, session_id: str, node: Node) -> None: ...

    @abstractmethod
    def get_node(self, session_id: str, node_id: NodeId) -> Node: ...

    @abstractmethod
    def get_nodes(self, session_id: str, node_ids: tuple[NodeId, ...]) -> tuple[Node | None, ...]:
        """Read up to 1000 identities atomically, preserving input order and duplicates.

        Missing nodes occupy None slots. A missing or expired tree raises ValueError,
        including for an empty batch. Returned nodes contain independent JSON.
        """
        ...

    @abstractmethod
    def list_nodes(
        self, session_id: str, *, kind: str | None = None, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Node]: ...

    @abstractmethod
    def list_children(
        self,
        session_id: str,
        parent_id: NodeId | None,
        *,
        kind: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[Node]: ...

    @abstractmethod
    def list_history(
        self, session_id: str, from_node: NodeId, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Node]: ...

    @abstractmethod
    def close(self) -> None: ...

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


class AsyncStore(ABC):
    """Async equivalent of SyncStore with the same guarantees."""

    @abstractmethod
    async def create_session(
        self, session_id: str, *, kind: str = "session", ttl: float | None = None
    ) -> SessionInfo: ...

    @abstractmethod
    async def get_session(self, session_id: str) -> SessionInfo | None: ...

    @abstractmethod
    async def set_session_ttl(self, session_id: str, ttl: float | None) -> SessionInfo: ...

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool: ...

    @abstractmethod
    async def list_sessions(
        self, *, kind: str | None = None, prefix: str = "", limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[SessionInfo]: ...

    @abstractmethod
    async def append(self, session_id: str, node: Node) -> None: ...

    @abstractmethod
    async def get_node(self, session_id: str, node_id: NodeId) -> Node: ...

    @abstractmethod
    async def get_nodes(self, session_id: str, node_ids: tuple[NodeId, ...]) -> tuple[Node | None, ...]:
        """Read up to 1000 identities atomically, preserving input order and duplicates.

        Missing nodes occupy None slots. A missing or expired tree raises ValueError,
        including for an empty batch. Returned nodes contain independent JSON.
        """
        ...

    @abstractmethod
    async def list_nodes(
        self, session_id: str, *, kind: str | None = None, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Node]: ...

    @abstractmethod
    async def list_children(
        self,
        session_id: str,
        parent_id: NodeId | None,
        *,
        kind: str | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> Page[Node]: ...

    @abstractmethod
    async def list_history(
        self, session_id: str, from_node: NodeId, *, limit: int = DEFAULT_PAGE_SIZE, cursor: str | None = None
    ) -> Page[Node]: ...

    @abstractmethod
    async def close(self) -> None: ...

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()
