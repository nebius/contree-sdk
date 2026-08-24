from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HistoryEntry:
    id: int
    session_id: str
    image_uuid: str
    parent_id: int | None
    kind: str
    title: str
    operation_uuid: str | None
    exit_code: int | None
    created_at: datetime
    files: tuple[str, ...] = ()


@dataclass(frozen=True)
class SessionMetadata:
    cwd: str | None
    env: dict[str, str]


class SyncStore(ABC):
    """A session's durable history: a DAG of images with named branch pointers (sync).

    One store instance may hold many sessions, multiplexed by `session_id`.
    """

    @abstractmethod
    def append(
        self,
        session_id: str,
        *,
        image_uuid: str,
        parent_id: int | None,
        kind: str = "",
        title: str = "",
        operation_uuid: str | None = None,
        exit_code: int | None = None,
        branch: str | None = None,
        files: tuple[str, ...] = (),
    ) -> HistoryEntry:
        """Insert an entry under `parent_id` and advance `branch` (default: active) to it."""

    @abstractmethod
    def get_entry(self, session_id: str, history_id: int) -> HistoryEntry: ...

    @abstractmethod
    def get_session_metadata(self, session_id: str) -> SessionMetadata:
        """Return current cwd/env for `session_id`; `SessionMetadata(cwd=None, env={})` if unset."""

    @abstractmethod
    def set_session_cwd(self, session_id: str, cwd: str | None) -> None: ...

    @abstractmethod
    def set_session_env(self, session_id: str, updates: dict[str, str | None]) -> None:
        """Merge `updates` into the session's env; a `None` value unsets that key."""

    @abstractmethod
    def tip(self, session_id: str, branch: str | None = None) -> HistoryEntry | None:
        """Return the entry the (active or named) branch points to, or None if it has no history yet."""

    @abstractmethod
    def navigate(self, session_id: str, target: int) -> HistoryEntry:
        """Move the active branch to `target` (absolute id if >0, else N steps back)."""

    @abstractmethod
    def rollback(self, session_id: str, steps: int = 1) -> HistoryEntry:
        """Sugar for navigate(session_id, -steps)."""

    @abstractmethod
    def navigate_forward(self, session_id: str, steps: int = 1) -> HistoryEntry:
        """Walk forward, picking the latest child at each branch point."""

    @abstractmethod
    def create_branch(self, session_id: str, name: str, *, from_branch: str | None = None) -> None: ...

    @abstractmethod
    def switch_branch(self, session_id: str, name: str) -> HistoryEntry: ...

    @abstractmethod
    def list_branches(self, session_id: str) -> list[tuple[str, bool]]:
        """(branch_name, is_active) pairs."""

    @abstractmethod
    def delete_branch(self, session_id: str, name: str) -> None: ...

    @abstractmethod
    def active_branch(self, session_id: str) -> str | None: ...

    @abstractmethod
    def list_sessions(self) -> list[str]: ...

    @abstractmethod
    def find_session(self, name: str) -> str:
        """Suffix or exact match against known session ids; raises ValueError if ambiguous or missing."""

    @abstractmethod
    def delete_session(self, session_id: str) -> bool: ...

    @abstractmethod
    def history_dag(self, session_id: str) -> tuple[list[HistoryEntry], dict[int, list[str]]]:
        """All entries (root to tip order) + {history_id: [branch names pointing here]}."""


class AsyncStore(ABC):
    """A session's durable history: a DAG of images with named branch pointers (async).

    One store instance may hold many sessions, multiplexed by `session_id`.
    """

    @abstractmethod
    async def append(
        self,
        session_id: str,
        *,
        image_uuid: str,
        parent_id: int | None,
        kind: str = "",
        title: str = "",
        operation_uuid: str | None = None,
        exit_code: int | None = None,
        branch: str | None = None,
        files: tuple[str, ...] = (),
    ) -> HistoryEntry:
        """Insert an entry under `parent_id` and advance `branch` (default: active) to it."""

    @abstractmethod
    async def get_entry(self, session_id: str, history_id: int) -> HistoryEntry: ...

    @abstractmethod
    async def get_session_metadata(self, session_id: str) -> SessionMetadata:
        """Return current cwd/env for `session_id`; `SessionMetadata(cwd=None, env={})` if unset."""

    @abstractmethod
    async def set_session_cwd(self, session_id: str, cwd: str | None) -> None: ...

    @abstractmethod
    async def set_session_env(self, session_id: str, updates: dict[str, str | None]) -> None:
        """Merge `updates` into the session's env; a `None` value unsets that key."""

    @abstractmethod
    async def tip(self, session_id: str, branch: str | None = None) -> HistoryEntry | None:
        """Return the entry the (active or named) branch points to, or None if it has no history yet."""

    @abstractmethod
    async def navigate(self, session_id: str, target: int) -> HistoryEntry:
        """Move the active branch to `target` (absolute id if >0, else N steps back)."""

    @abstractmethod
    async def rollback(self, session_id: str, steps: int = 1) -> HistoryEntry:
        """Sugar for navigate(session_id, -steps)."""

    @abstractmethod
    async def navigate_forward(self, session_id: str, steps: int = 1) -> HistoryEntry:
        """Walk forward, picking the latest child at each branch point."""

    @abstractmethod
    async def create_branch(self, session_id: str, name: str, *, from_branch: str | None = None) -> None: ...

    @abstractmethod
    async def switch_branch(self, session_id: str, name: str) -> HistoryEntry: ...

    @abstractmethod
    async def list_branches(self, session_id: str) -> list[tuple[str, bool]]:
        """(branch_name, is_active) pairs."""

    @abstractmethod
    async def delete_branch(self, session_id: str, name: str) -> None: ...

    @abstractmethod
    async def active_branch(self, session_id: str) -> str | None: ...

    @abstractmethod
    async def list_sessions(self) -> list[str]: ...

    @abstractmethod
    async def find_session(self, name: str) -> str:
        """Suffix or exact match against known session ids; raises ValueError if ambiguous or missing."""

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool: ...

    @abstractmethod
    async def history_dag(self, session_id: str) -> tuple[list[HistoryEntry], dict[int, list[str]]]:
        """All entries (root to tip order) + {history_id: [branch names pointing here]}."""
