from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from types import EllipsisType

from contree_sdk.compat import Self
from contree_sdk.exceptions import SessionConflictError
from contree_sdk.store.models import HistoryEntry, HistorySnapshot, SessionMetadata, SessionSummary, StagedFile
from contree_sdk.store.operations import OperationRecord


class SyncStore(ABC):  # noqa: PLR0904 - public extension contract
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
        attachments: tuple[StagedFile, ...] = (),
        applied_files: tuple[str, ...] = (),
        expected_tip: int | EllipsisType | None = ...,
    ) -> HistoryEntry:
        """Append an entry and advance the named or active branch atomically.

        If supplied, `expected_tip` must match the branch tip. None requires
        a new branch. A mismatch raises SessionConflictError without changes.
        """

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

    @abstractmethod
    def read_session(self, session_id: str) -> HistorySnapshot:
        """Read entries, branch pointers, and metadata in one consistent snapshot.

        Raise ValueError for an unknown session. Never change its active branch,
        head, or metadata. The returned view must not retain live store state.
        """

    def register_operation(self, record: OperationRecord) -> OperationRecord:
        """Persist a pending operation; identical registration is idempotent.

        Reject a changed context or a source entry outside the session.
        """
        raise NotImplementedError("this store does not support detached operations")

    def get_operation(self, session_id: str, operation_uuid: str) -> OperationRecord:
        """Read one registered operation; raise ValueError when absent."""
        raise NotImplementedError("this store does not support detached operations")

    def list_operations(self, session_id: str, *, pending_only: bool = True) -> tuple[OperationRecord, ...]:
        """List registered operations in UUID order without modifying them."""
        raise NotImplementedError("this store does not support detached operations")

    def finish_operation(
        self,
        session_id: str,
        operation_uuid: str,
        response_json: str,
        *,
        image_uuid: str | None = None,
        exit_code: int | None = None,
        branch: str | None = None,
    ) -> OperationRecord:
        """Atomically store the first final response and optional history entry.

        With image_uuid, append on the recorded branch using its source parent
        as expected_tip. An explicit different branch must not exist. Never
        switch the active branch. A conflict leaves the entire record pending.
        Without image_uuid, store the response without appending history.
        Repeated calls return the first completed record without further writes.
        """
        raise NotImplementedError("this store does not support detached operations")

    def stage_files(
        self,
        session_id: str,
        attachments: Iterable[StagedFile],
        *,
        branch: str | None = None,
        expected_tip: int | EllipsisType | None = ...,
    ) -> HistoryEntry:
        """Append staging to an existing branch without starting a VM.

        Returns:
            The staging entry on the selected branch.

        Raises:
            ValueError: The batch is empty, paths repeat, or the session or branch is missing.
            SessionConflictError: The selected branch changed before staging could be saved.

        """
        batch = tuple(attachments)
        if not batch:
            raise ValueError("staging requires at least one attachment")
        snapshot = self.read_session(session_id)
        parent = snapshot.resolve(branch=branch)
        name = branch if branch is not None else snapshot.summary().active_branch
        if expected_tip is not Ellipsis and parent.id != expected_tip:
            raise SessionConflictError(f"branch {name!r} changed in session {session_id!r}")
        return self.append(
            session_id,
            image_uuid=parent.image_uuid,
            parent_id=parent.id,
            kind="stage",
            branch=name,
            attachments=batch,
            expected_tip=parent.id,
        )

    def pending_files(
        self,
        session_id: str,
        *,
        history_id: int | None = None,
        branch: str | None = None,
    ) -> tuple[StagedFile, ...]:
        snapshot = self.read_session(session_id)
        return snapshot.pending_files(history_id=history_id, branch=branch)

    def resolve_history(
        self, session_id: str, *, history_id: int | None = None, offset: int = 0, branch: str | None = None
    ) -> HistoryEntry:
        snapshot = self.read_session(session_id)
        return snapshot.resolve(history_id=history_id, offset=offset, branch=branch)

    def resolve_operation(
        self, session_id: str, *, history_id: int | None = None, offset: int = 0, branch: str | None = None
    ) -> str:
        snapshot = self.read_session(session_id)
        return snapshot.resolve_operation(history_id=history_id, offset=offset, branch=branch)

    def get_session_summary(self, session_id: str) -> SessionSummary:
        return (self.read_session(session_id)).summary()

    def list_session_summaries(self, *, prefix: str = "") -> list[SessionSummary]:
        """Read per-session summaries in ID order, with a literal prefix filter.

        Each summary is consistent. The entire list is not a cross-session transaction.

        Returns:
            Matching session summaries. Session names are not abbreviated.

        """
        return [self.get_session_summary(name) for name in self.list_sessions() if name.startswith(prefix)]

    @abstractmethod
    def prune_branches(
        self, session_id: str, *, prefix: str, keep: Iterable[str] = (), dry_run: bool = False
    ) -> tuple[str, ...]:
        """Atomically remove matching branch pointers, retaining active and keep names.

        Require a nonempty literal prefix. Never remove history, metadata, or images.
        With dry_run, return the selected names without changing the store.
        An unknown session raises ValueError. Names in keep need not exist.
        """

    def close(self) -> None:  # noqa: B027 - public extension contract
        """Release owned resources. The default implementation has no resources."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()


class AsyncStore(ABC):  # noqa: PLR0904 - public extension contract
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
        attachments: tuple[StagedFile, ...] = (),
        applied_files: tuple[str, ...] = (),
        expected_tip: int | EllipsisType | None = ...,
    ) -> HistoryEntry:
        """Append an entry and advance the named or active branch atomically.

        If supplied, `expected_tip` must match the branch tip. None requires
        a new branch. A mismatch raises SessionConflictError without changes.
        """

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

    @abstractmethod
    async def read_session(self, session_id: str) -> HistorySnapshot:
        """Read entries, branch pointers, and metadata in one consistent snapshot.

        Raise ValueError for an unknown session. Never change its active branch,
        head, or metadata. The returned view must not retain live store state.
        """

    async def register_operation(self, record: OperationRecord) -> OperationRecord:
        """Persist a pending operation; identical registration is idempotent.

        Reject a changed context or a source entry outside the session.
        """
        raise NotImplementedError("this store does not support detached operations")

    async def get_operation(self, session_id: str, operation_uuid: str) -> OperationRecord:
        """Read one registered operation; raise ValueError when absent."""
        raise NotImplementedError("this store does not support detached operations")

    async def list_operations(self, session_id: str, *, pending_only: bool = True) -> tuple[OperationRecord, ...]:
        """List registered operations in UUID order without modifying them."""
        raise NotImplementedError("this store does not support detached operations")

    async def finish_operation(
        self,
        session_id: str,
        operation_uuid: str,
        response_json: str,
        *,
        image_uuid: str | None = None,
        exit_code: int | None = None,
        branch: str | None = None,
    ) -> OperationRecord:
        """Atomically store the first final response and optional history entry.

        With image_uuid, append on the recorded branch using its source parent
        as expected_tip. An explicit different branch must not exist. Never
        switch the active branch. A conflict leaves the entire record pending.
        Without image_uuid, store the response without appending history.
        Repeated calls return the first completed record without further writes.
        """
        raise NotImplementedError("this store does not support detached operations")

    async def stage_files(
        self,
        session_id: str,
        attachments: Iterable[StagedFile],
        *,
        branch: str | None = None,
        expected_tip: int | EllipsisType | None = ...,
    ) -> HistoryEntry:
        """Append staging to an existing branch without starting a VM.

        Returns:
            The staging entry on the selected branch.

        Raises:
            ValueError: The batch is empty, paths repeat, or the session or branch is missing.
            SessionConflictError: The selected branch changed before staging could be saved.

        """
        batch = tuple(attachments)
        if not batch:
            raise ValueError("staging requires at least one attachment")
        snapshot = await self.read_session(session_id)
        parent = snapshot.resolve(branch=branch)
        name = branch if branch is not None else snapshot.summary().active_branch
        if expected_tip is not Ellipsis and parent.id != expected_tip:
            raise SessionConflictError(f"branch {name!r} changed in session {session_id!r}")
        return await self.append(
            session_id,
            image_uuid=parent.image_uuid,
            parent_id=parent.id,
            kind="stage",
            branch=name,
            attachments=batch,
            expected_tip=parent.id,
        )

    async def pending_files(
        self,
        session_id: str,
        *,
        history_id: int | None = None,
        branch: str | None = None,
    ) -> tuple[StagedFile, ...]:
        snapshot = await self.read_session(session_id)
        return snapshot.pending_files(history_id=history_id, branch=branch)

    async def resolve_history(
        self, session_id: str, *, history_id: int | None = None, offset: int = 0, branch: str | None = None
    ) -> HistoryEntry:
        snapshot = await self.read_session(session_id)
        return snapshot.resolve(history_id=history_id, offset=offset, branch=branch)

    async def resolve_operation(
        self, session_id: str, *, history_id: int | None = None, offset: int = 0, branch: str | None = None
    ) -> str:
        snapshot = await self.read_session(session_id)
        return snapshot.resolve_operation(history_id=history_id, offset=offset, branch=branch)

    async def get_session_summary(self, session_id: str) -> SessionSummary:
        return (await self.read_session(session_id)).summary()

    async def list_session_summaries(self, *, prefix: str = "") -> list[SessionSummary]:
        """Read per-session summaries in ID order, with a literal prefix filter.

        Each summary is consistent. The entire list is not a cross-session transaction.

        Returns:
            Matching session summaries. Session names are not abbreviated.

        """
        return [await self.get_session_summary(name) for name in await self.list_sessions() if name.startswith(prefix)]

    @abstractmethod
    async def prune_branches(
        self, session_id: str, *, prefix: str, keep: Iterable[str] = (), dry_run: bool = False
    ) -> tuple[str, ...]:
        """Atomically remove matching branch pointers, retaining active and keep names.

        Require a nonempty literal prefix. Never remove history, metadata, or images.
        With dry_run, return the selected names without changing the store.
        An unknown session raises ValueError. Names in keep need not exist.
        """

    async def close(self) -> None:  # noqa: B027 - public extension contract
        """Release owned resources. The default implementation has no resources."""

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()
