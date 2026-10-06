"""Immutable records and queries over a snapshot of one session's history."""

from __future__ import annotations

from collections.abc import Iterable
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


@dataclass(frozen=True)
class BranchInfo:
    name: str
    tip: HistoryEntry
    is_active: bool


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    active_branch: str
    tip: HistoryEntry
    branches: tuple[BranchInfo, ...]
    entry_count: int
    created_at: datetime
    last_entry_at: datetime
    metadata: SessionMetadata


@dataclass(frozen=True)
class HistorySnapshot:
    """A detached view of one session; resolving positions never changes the store."""

    session_id: str
    entries: tuple[HistoryEntry, ...]
    branches: tuple[BranchInfo, ...]
    metadata: SessionMetadata

    def resolve(self, *, history_id: int | None = None, offset: int = 0, branch: str | None = None) -> HistoryEntry:
        """Resolve an ID or branch head, then follow the signed offset.

        Negative offsets follow parents. Positive offsets choose the child with
        the greatest ID, including entries no branch currently references.

        Returns:
            The selected entry from this snapshot.

        Raises:
            ValueError: Selectors conflict, an entry is missing, or the offset is out of range.

        """
        if history_id is not None and (history_id <= 0 or branch is not None):
            raise ValueError("history_id must be positive and cannot be combined with branch")
        entries = {entry.id: entry for entry in self.entries if entry.session_id == self.session_id}
        if history_id is None:
            heads = [
                item.tip.id for item in self.branches if item.name == branch or (branch is None and item.is_active)
            ]
            if len(heads) != 1:
                raise ValueError(f"branch {branch!r} not found in session {self.session_id!r}")
            history_id = heads[0]
        if history_id not in entries:
            raise ValueError(f"history entry {history_id} not found in session {self.session_id!r}")
        entry = entries[history_id]
        children: dict[int, int] = {}
        if offset > 0:
            for candidate in entries.values():
                if candidate.parent_id is not None:
                    children[candidate.parent_id] = max(candidate.id, children.get(candidate.parent_id, 0))
        for step in range(abs(offset)):
            next_id = entry.parent_id if offset < 0 else children.get(entry.id)
            if next_id is None or next_id not in entries:
                raise ValueError(f"cannot resolve offset {offset}: only {step} steps available")
            entry = entries[next_id]
        return entry

    def resolve_operation(self, *, history_id: int | None = None, offset: int = 0, branch: str | None = None) -> str:
        """Resolve the operation of exactly one entry, without falling back to its parents.

        Returns:
            The recorded operation UUID.

        Raises:
            ValueError: The selected entry has no operation UUID, or its position is invalid.

        """
        entry = self.resolve(history_id=history_id, offset=offset, branch=branch)
        if not entry.operation_uuid:
            raise ValueError(f"history entry {entry.id} has no operation UUID")
        return entry.operation_uuid

    def summary(self) -> SessionSummary:
        """Summarize the snapshot, including all entries in its DAG.

        Returns:
            Branch heads, metadata, and append timestamps. last_entry_at is not a navigation timestamp.

        """
        active = next(item for item in self.branches if item.is_active)
        return SessionSummary(
            session_id=self.session_id,
            active_branch=active.name,
            tip=active.tip,
            branches=self.branches,
            entry_count=len(self.entries),
            created_at=min(entry.created_at for entry in self.entries),
            last_entry_at=max(entry.created_at for entry in self.entries),
            metadata=self.metadata,
        )


def history_snapshot(
    session_id: str,
    active: str | None,
    entries: Iterable[HistoryEntry],
    branch_map: dict[int, list[str]],
    metadata: SessionMetadata,
) -> HistorySnapshot:
    ordered = tuple(sorted(entries, key=lambda item: item.id))
    by_id = {item.id: item for item in ordered}
    branches = tuple(
        sorted(
            (
                BranchInfo(name, by_id[entry_id], name == active)
                for entry_id, names in branch_map.items()
                for name in names
            ),
            key=lambda item: item.name,
        )
    )
    if active is None or not any(item.is_active for item in branches):
        raise ValueError(f"session {session_id!r} not found")
    return HistorySnapshot(session_id, ordered, branches, metadata)


def prune_selection(branches: Iterable[tuple[str, bool]], prefix: str, keep: frozenset[str]) -> tuple[str, ...]:
    return tuple(
        sorted(name for name, active in branches if not active and name.startswith(prefix) and name not in keep)
    )


def validate_prune(prefix: str, keep: Iterable[str]) -> frozenset[str]:
    if not prefix:
        raise ValueError("pruning requires a nonempty branch prefix")
    if isinstance(keep, str):
        raise TypeError("keep must be an iterable of branch names, not one string")
    return frozenset(keep)
