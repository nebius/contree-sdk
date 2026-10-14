"""Immutable records and queries over a snapshot of one session's history."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from types import EllipsisType

from contree_client.models import FileSpec


@dataclass(frozen=True)
class StagedFile:
    """An uploaded file and its destination metadata, detached from a local source."""

    path: str
    uuid: str
    uid: int | None = 0
    gid: int | None = 0
    mode: int | None = 0o644

    def __post_init__(self) -> None:
        if not self.path or not self.uuid:
            raise ValueError("staged files require a destination path and upload UUID")
        object.__setattr__(self, "path", str(PurePosixPath(self.path)))

    @classmethod
    def from_spec(cls, path: str, spec: FileSpec) -> StagedFile:
        """Copy a transport attachment, preserving omitted permission fields.

        Returns:
            A detached attachment with an octal mode converted to an integer.

        Raises:
            ValueError: The upload UUID is missing or the mode is not octal.

        """
        if spec.uuid is Ellipsis:
            raise ValueError("staged files require an upload UUID")
        mode = None if isinstance(spec.mode, EllipsisType) else spec.mode
        return cls(
            path,
            spec.uuid,
            None if isinstance(spec.uid, EllipsisType) else spec.uid,
            None if isinstance(spec.gid, EllipsisType) else spec.gid,
            int(mode, 8) if isinstance(mode, str) else mode,
        )

    def as_spec(self) -> FileSpec:
        """Create a transport attachment without reading or uploading its source.

        Returns:
            A new FileSpec with the recorded metadata.

        """
        return FileSpec(
            uuid=self.uuid,
            uid=self.uid if self.uid is not None else ...,
            gid=self.gid if self.gid is not None else ...,
            mode=self.mode if self.mode is not None else ...,
        )


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
    attachments: tuple[StagedFile, ...] = ()
    applied_files: tuple[str, ...] = ()


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

    def pending_files(self, *, history_id: int | None = None, branch: str | None = None) -> tuple[StagedFile, ...]:
        """Read the newest unapplied attachment per path on the selected ancestry.

        Returns:
            Attachments ordered by destination path.

        """
        entry = self.resolve(history_id=history_id, branch=branch)
        entries = {item.id: item for item in self.entries if item.session_id == self.session_id}
        seen: set[str] = set()
        pending: dict[str, StagedFile] = {}
        while True:
            for attachment in entry.attachments:
                if attachment.path not in seen:
                    pending[attachment.path] = attachment
                    seen.add(attachment.path)
            seen.update(entry.applied_files)
            if entry.parent_id is None:
                break
            entry = entries[entry.parent_id]
        return tuple(pending[path] for path in sorted(pending))

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


def validate_attachments(attachments: tuple[StagedFile, ...]) -> None:
    if len({item.path for item in attachments}) != len(attachments):
        raise ValueError("duplicate staged destination path")
