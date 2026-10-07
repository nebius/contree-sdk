from __future__ import annotations

import threading
from asyncio import Lock
from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime, timezone
from types import EllipsisType

from contree_sdk.exceptions import SessionConflictError
from contree_sdk.store.base import AsyncStore, HistoryEntry, SessionMetadata, SyncStore
from contree_sdk.store.models import (
    HistorySnapshot,
    StagedFile,
    history_snapshot,
    prune_selection,
    validate_attachments,
    validate_prune,
)
from contree_sdk.store.operations import OperationRecord, validate_registration


class SyncMemoryStore(SyncStore):  # noqa: PLR0904 - public store contract
    """Pure in-process Store: one instance, one process's history graph."""

    def __init__(self) -> None:
        self.entries: dict[int, HistoryEntry] = {}
        self.operations: dict[tuple[str, str], OperationRecord] = {}
        self.next_id = 1
        self.branches: dict[str, dict[str, int]] = {}
        self.active_branches: dict[str, str] = {}
        self.cwds: dict[str, str] = {}
        self.envs: dict[str, dict[str, str]] = {}
        self.lock = threading.Lock()

    def branch_tip_id(self, session_id: str, branch: str) -> int | None:
        return self.branches.get(session_id, {}).get(branch)

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
        validate_attachments(attachments)
        with self.lock:
            return self._append(
                session_id,
                image_uuid=image_uuid,
                parent_id=parent_id,
                kind=kind,
                title=title,
                operation_uuid=operation_uuid,
                exit_code=exit_code,
                branch=branch,
                files=files,
                attachments=attachments,
                applied_files=applied_files,
                expected_tip=expected_tip,
            )

    def _append(
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
        branch_name = branch or self.active_branches.get(session_id) or "main"
        if expected_tip is not Ellipsis and self.branch_tip_id(session_id, branch_name) != expected_tip:
            raise SessionConflictError(f"branch {branch_name!r} changed in session {session_id!r}")
        if parent_id is not None:
            self.get_entry(session_id, parent_id)
        entry = HistoryEntry(
            id=self.next_id,
            session_id=session_id,
            image_uuid=image_uuid,
            parent_id=parent_id,
            kind=kind,
            title=title,
            operation_uuid=operation_uuid,
            exit_code=exit_code,
            created_at=datetime.now(timezone.utc),
            files=files,
            attachments=tuple(attachments),
            applied_files=tuple(applied_files),
        )
        self.entries[entry.id] = entry
        self.next_id += 1
        self.branches.setdefault(session_id, {})[branch_name] = entry.id
        self.active_branches.setdefault(session_id, branch_name)
        return entry

    def register_operation(self, record: OperationRecord) -> OperationRecord:
        with self.lock:
            parent = self.get_entry(record.session_id, record.parent_id)
            if parent.image_uuid != record.image_uuid:
                raise ValueError("operation source image does not match its history entry")
            key = (record.session_id, record.uuid)
            saved = validate_registration(record, self.operations.get(key))
            self.operations[key] = saved
            return saved

    def get_operation(self, session_id: str, operation_uuid: str) -> OperationRecord:
        with self.lock:
            record = self.operations.get((session_id, operation_uuid))
            if record is None:
                raise ValueError("operation is not registered in this session")
            return record

    def list_operations(self, session_id: str, *, pending_only: bool = True) -> tuple[OperationRecord, ...]:
        with self.lock:
            return tuple(
                record
                for (session, _), record in sorted(self.operations.items())
                if session == session_id and (not pending_only or record.pending)
            )

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
        with self.lock:
            key = (session_id, operation_uuid)
            record = self.operations.get(key)
            if record is None:
                raise ValueError("operation is not registered in this session")
            if not record.pending:
                return record
            completed = replace(record, response_json=response_json)
            if image_uuid is not None:
                if record.disposable:
                    raise ValueError("cannot commit a disposable operation")
                entry = self._append(
                    session_id,
                    image_uuid=image_uuid,
                    parent_id=record.parent_id,
                    kind="run",
                    title=record.title,
                    operation_uuid=record.uuid,
                    exit_code=exit_code,
                    branch=branch or record.branch,
                    files=record.files,
                    applied_files=record.files,
                    expected_tip=record.parent_id if branch is None or branch == record.branch else None,
                )
                completed = replace(completed, history_id=entry.id)
            self.operations[key] = completed
            return completed

    def get_entry(self, session_id: str, history_id: int) -> HistoryEntry:
        entry = self.entries.get(history_id)
        if entry is None or entry.session_id != session_id:
            raise ValueError(f"history entry {history_id} not found in session {session_id!r}")
        return entry

    def get_session_metadata(self, session_id: str) -> SessionMetadata:
        with self.lock:
            return SessionMetadata(cwd=self.cwds.get(session_id), env=dict(self.envs.get(session_id, {})))

    def set_session_cwd(self, session_id: str, cwd: str | None) -> None:
        with self.lock:
            if cwd is None:
                self.cwds.pop(session_id, None)
            else:
                self.cwds[session_id] = cwd

    def set_session_env(self, session_id: str, updates: dict[str, str | None]) -> None:
        with self.lock:
            env = self.envs.setdefault(session_id, {})
            for key, value in updates.items():
                if value is None:
                    env.pop(key, None)
                else:
                    env[key] = value

    def tip(self, session_id: str, branch: str | None = None) -> HistoryEntry | None:
        branch_name = branch or self.active_branches.get(session_id)
        if branch_name is None:
            return None
        history_id = self.branch_tip_id(session_id, branch_name)
        return None if history_id is None else self.get_entry(session_id, history_id)

    def navigate(self, session_id: str, target: int) -> HistoryEntry:
        if target == 0:
            raise ValueError("navigation target must not be 0")
        with self.lock:
            branch = self.active_branches.get(session_id)
            if branch is None:
                raise ValueError(f"no active session {session_id!r}")
            if target > 0:
                current_id = target
                self.get_entry(session_id, current_id)
            else:
                tip_id = self.branch_tip_id(session_id, branch)
                if tip_id is None:
                    raise ValueError(f"no active session {session_id!r}")
                current_id = tip_id
                for step in range(-target):
                    entry = self.get_entry(session_id, current_id)
                    if entry.parent_id is None:
                        raise ValueError(f"cannot go back {-target} steps: only {step} ancestors available")
                    current_id = entry.parent_id
            self.branches[session_id][branch] = current_id
            return self.get_entry(session_id, current_id)

    def rollback(self, session_id: str, steps: int = 1) -> HistoryEntry:
        if steps < 1:
            raise ValueError("rollback steps must be >= 1")
        return self.navigate(session_id, -steps)

    def navigate_forward(self, session_id: str, steps: int = 1) -> HistoryEntry:
        if steps < 1:
            raise ValueError("forward steps must be >= 1")
        with self.lock:
            branch = self.active_branches.get(session_id)
            if branch is None:
                raise ValueError(f"no active session {session_id!r}")
            current_id = self.branch_tip_id(session_id, branch)
            if current_id is None:
                raise ValueError(f"no active session {session_id!r}")
            for step in range(steps):
                children = sorted(
                    entry.id
                    for entry in self.entries.values()
                    if entry.session_id == session_id and entry.parent_id == current_id
                )
                if not children:
                    raise ValueError(f"cannot go forward {steps} steps: only {step} children available")
                current_id = children[-1]
            self.branches[session_id][branch] = current_id
            return self.get_entry(session_id, current_id)

    def create_branch(self, session_id: str, name: str, *, from_branch: str | None = None) -> None:
        with self.lock:
            source = from_branch or self.active_branches.get(session_id)
            if source is None:
                raise ValueError(f"no active session {session_id!r}")
            history_id = self.branch_tip_id(session_id, source)
            if history_id is None:
                raise ValueError(f"source branch {source!r} does not exist")
            branches = self.branches.setdefault(session_id, {})
            if name in branches:
                raise ValueError(f"branch {name!r} already exists")
            branches[name] = history_id

    def switch_branch(self, session_id: str, name: str) -> HistoryEntry:
        with self.lock:
            history_id = self.branch_tip_id(session_id, name)
            if history_id is None:
                raise ValueError(f"branch {name!r} does not exist")
            self.active_branches[session_id] = name
            return self.get_entry(session_id, history_id)

    def list_branches(self, session_id: str) -> list[tuple[str, bool]]:
        active = self.active_branches.get(session_id)
        if active is None:
            return []
        return sorted((name, name == active) for name in self.branches.get(session_id, {}))

    def delete_branch(self, session_id: str, name: str) -> None:
        with self.lock:
            if name == self.active_branches.get(session_id):
                raise ValueError("cannot delete the active branch")
            branches = self.branches.get(session_id, {})
            if name not in branches:
                raise ValueError(f"branch {name!r} does not exist")
            del branches[name]

    def active_branch(self, session_id: str) -> str | None:
        return self.active_branches.get(session_id)

    def list_sessions(self) -> list[str]:
        return sorted(self.active_branches)

    def read_session(self, session_id: str) -> HistorySnapshot:
        with self.lock:
            entries, branches = self.history_dag(session_id)
            metadata = SessionMetadata(self.cwds.get(session_id), dict(self.envs.get(session_id, {})))
            return history_snapshot(session_id, self.active_branches.get(session_id), entries, branches, metadata)

    def prune_branches(
        self, session_id: str, *, prefix: str, keep: Iterable[str] = (), dry_run: bool = False
    ) -> tuple[str, ...]:
        retained = validate_prune(prefix, keep)
        with self.lock:
            if session_id not in self.active_branches:
                raise ValueError(f"session {session_id!r} not found")
            selected = prune_selection(self.list_branches(session_id), prefix, retained)
            if not dry_run:
                for name in selected:
                    del self.branches[session_id][name]
            return selected

    def find_session(self, name: str) -> str:
        if name in self.active_branches:
            return name
        matches = [session_id for session_id in self.active_branches if session_id.endswith(f"_{name}")]
        if not matches:
            raise ValueError(f"session {name!r} not found")
        if len(matches) > 1:
            raise ValueError(f"ambiguous session {name!r}: matches {', '.join(matches)}")
        return matches[0]

    def delete_session(self, session_id: str) -> bool:
        with self.lock:
            if session_id not in self.active_branches:
                return False
            for history_id in [entry.id for entry in self.entries.values() if entry.session_id == session_id]:
                del self.entries[history_id]
            del self.branches[session_id]
            del self.active_branches[session_id]
            self.cwds.pop(session_id, None)
            self.envs.pop(session_id, None)
            self.operations = {key: value for key, value in self.operations.items() if key[0] != session_id}
            return True

    def history_dag(self, session_id: str) -> tuple[list[HistoryEntry], dict[int, list[str]]]:
        entries = sorted(
            (entry for entry in self.entries.values() if entry.session_id == session_id), key=lambda entry: entry.id
        )
        branch_map: dict[int, list[str]] = {}
        for name, history_id in self.branches.get(session_id, {}).items():
            branch_map.setdefault(history_id, []).append(name)
        return entries, branch_map


class AsyncMemoryStore(AsyncStore):  # noqa: PLR0904 - public store contract
    """Pure in-process Store: one instance, one process's history graph."""

    def __init__(self) -> None:
        self.entries: dict[int, HistoryEntry] = {}
        self.operations: dict[tuple[str, str], OperationRecord] = {}
        self.next_id = 1
        self.branches: dict[str, dict[str, int]] = {}
        self.active_branches: dict[str, str] = {}
        self.cwds: dict[str, str] = {}
        self.envs: dict[str, dict[str, str]] = {}
        self.lock = Lock()

    def branch_tip_id(self, session_id: str, branch: str) -> int | None:
        return self.branches.get(session_id, {}).get(branch)

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
        validate_attachments(attachments)
        async with self.lock:
            return await self._append(
                session_id,
                image_uuid=image_uuid,
                parent_id=parent_id,
                kind=kind,
                title=title,
                operation_uuid=operation_uuid,
                exit_code=exit_code,
                branch=branch,
                files=files,
                attachments=attachments,
                applied_files=applied_files,
                expected_tip=expected_tip,
            )

    async def _append(
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
        branch_name = branch or self.active_branches.get(session_id) or "main"
        if expected_tip is not Ellipsis and self.branch_tip_id(session_id, branch_name) != expected_tip:
            raise SessionConflictError(f"branch {branch_name!r} changed in session {session_id!r}")
        if parent_id is not None:
            await self.get_entry(session_id, parent_id)
        entry = HistoryEntry(
            id=self.next_id,
            session_id=session_id,
            image_uuid=image_uuid,
            parent_id=parent_id,
            kind=kind,
            title=title,
            operation_uuid=operation_uuid,
            exit_code=exit_code,
            created_at=datetime.now(timezone.utc),
            files=files,
            attachments=tuple(attachments),
            applied_files=tuple(applied_files),
        )
        self.entries[entry.id] = entry
        self.next_id += 1
        self.branches.setdefault(session_id, {})[branch_name] = entry.id
        self.active_branches.setdefault(session_id, branch_name)
        return entry

    async def register_operation(self, record: OperationRecord) -> OperationRecord:
        async with self.lock:
            parent = await self.get_entry(record.session_id, record.parent_id)
            if parent.image_uuid != record.image_uuid:
                raise ValueError("operation source image does not match its history entry")
            key = (record.session_id, record.uuid)
            saved = validate_registration(record, self.operations.get(key))
            self.operations[key] = saved
            return saved

    async def get_operation(self, session_id: str, operation_uuid: str) -> OperationRecord:
        async with self.lock:
            record = self.operations.get((session_id, operation_uuid))
            if record is None:
                raise ValueError("operation is not registered in this session")
            return record

    async def list_operations(self, session_id: str, *, pending_only: bool = True) -> tuple[OperationRecord, ...]:
        async with self.lock:
            return tuple(
                record
                for (session, _), record in sorted(self.operations.items())
                if session == session_id and (not pending_only or record.pending)
            )

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
        async with self.lock:
            key = (session_id, operation_uuid)
            record = self.operations.get(key)
            if record is None:
                raise ValueError("operation is not registered in this session")
            if not record.pending:
                return record
            completed = replace(record, response_json=response_json)
            if image_uuid is not None:
                if record.disposable:
                    raise ValueError("cannot commit a disposable operation")
                entry = await self._append(
                    session_id,
                    image_uuid=image_uuid,
                    parent_id=record.parent_id,
                    kind="run",
                    title=record.title,
                    operation_uuid=record.uuid,
                    exit_code=exit_code,
                    branch=branch or record.branch,
                    files=record.files,
                    applied_files=record.files,
                    expected_tip=record.parent_id if branch is None or branch == record.branch else None,
                )
                completed = replace(completed, history_id=entry.id)
            self.operations[key] = completed
            return completed

    async def get_entry(self, session_id: str, history_id: int) -> HistoryEntry:
        entry = self.entries.get(history_id)
        if entry is None or entry.session_id != session_id:
            raise ValueError(f"history entry {history_id} not found in session {session_id!r}")
        return entry

    async def get_session_metadata(self, session_id: str) -> SessionMetadata:
        async with self.lock:
            return SessionMetadata(cwd=self.cwds.get(session_id), env=dict(self.envs.get(session_id, {})))

    async def set_session_cwd(self, session_id: str, cwd: str | None) -> None:
        async with self.lock:
            if cwd is None:
                self.cwds.pop(session_id, None)
            else:
                self.cwds[session_id] = cwd

    async def set_session_env(self, session_id: str, updates: dict[str, str | None]) -> None:
        async with self.lock:
            env = self.envs.setdefault(session_id, {})
            for key, value in updates.items():
                if value is None:
                    env.pop(key, None)
                else:
                    env[key] = value

    async def tip(self, session_id: str, branch: str | None = None) -> HistoryEntry | None:
        branch_name = branch or self.active_branches.get(session_id)
        if branch_name is None:
            return None
        history_id = self.branch_tip_id(session_id, branch_name)
        return None if history_id is None else await self.get_entry(session_id, history_id)

    async def navigate(self, session_id: str, target: int) -> HistoryEntry:
        if target == 0:
            raise ValueError("navigation target must not be 0")
        async with self.lock:
            branch = self.active_branches.get(session_id)
            if branch is None:
                raise ValueError(f"no active session {session_id!r}")
            if target > 0:
                current_id = target
                await self.get_entry(session_id, current_id)
            else:
                tip_id = self.branch_tip_id(session_id, branch)
                if tip_id is None:
                    raise ValueError(f"no active session {session_id!r}")
                current_id = tip_id
                for step in range(-target):
                    entry = await self.get_entry(session_id, current_id)
                    if entry.parent_id is None:
                        raise ValueError(f"cannot go back {-target} steps: only {step} ancestors available")
                    current_id = entry.parent_id
            self.branches[session_id][branch] = current_id
            return await self.get_entry(session_id, current_id)

    async def rollback(self, session_id: str, steps: int = 1) -> HistoryEntry:
        if steps < 1:
            raise ValueError("rollback steps must be >= 1")
        return await self.navigate(session_id, -steps)

    async def navigate_forward(self, session_id: str, steps: int = 1) -> HistoryEntry:
        if steps < 1:
            raise ValueError("forward steps must be >= 1")
        async with self.lock:
            branch = self.active_branches.get(session_id)
            if branch is None:
                raise ValueError(f"no active session {session_id!r}")
            current_id = self.branch_tip_id(session_id, branch)
            if current_id is None:
                raise ValueError(f"no active session {session_id!r}")
            for step in range(steps):
                children = sorted(
                    entry.id
                    for entry in self.entries.values()
                    if entry.session_id == session_id and entry.parent_id == current_id
                )
                if not children:
                    raise ValueError(f"cannot go forward {steps} steps: only {step} children available")
                current_id = children[-1]
            self.branches[session_id][branch] = current_id
            return await self.get_entry(session_id, current_id)

    async def create_branch(self, session_id: str, name: str, *, from_branch: str | None = None) -> None:
        async with self.lock:
            source = from_branch or self.active_branches.get(session_id)
            if source is None:
                raise ValueError(f"no active session {session_id!r}")
            history_id = self.branch_tip_id(session_id, source)
            if history_id is None:
                raise ValueError(f"source branch {source!r} does not exist")
            branches = self.branches.setdefault(session_id, {})
            if name in branches:
                raise ValueError(f"branch {name!r} already exists")
            branches[name] = history_id

    async def switch_branch(self, session_id: str, name: str) -> HistoryEntry:
        async with self.lock:
            history_id = self.branch_tip_id(session_id, name)
            if history_id is None:
                raise ValueError(f"branch {name!r} does not exist")
            self.active_branches[session_id] = name
            return await self.get_entry(session_id, history_id)

    async def list_branches(self, session_id: str) -> list[tuple[str, bool]]:
        active = self.active_branches.get(session_id)
        if active is None:
            return []
        return sorted((name, name == active) for name in self.branches.get(session_id, {}))

    async def delete_branch(self, session_id: str, name: str) -> None:
        async with self.lock:
            if name == self.active_branches.get(session_id):
                raise ValueError("cannot delete the active branch")
            branches = self.branches.get(session_id, {})
            if name not in branches:
                raise ValueError(f"branch {name!r} does not exist")
            del branches[name]

    async def active_branch(self, session_id: str) -> str | None:
        return self.active_branches.get(session_id)

    async def list_sessions(self) -> list[str]:
        return sorted(self.active_branches)

    async def read_session(self, session_id: str) -> HistorySnapshot:
        async with self.lock:
            entries, branches = await self.history_dag(session_id)
            metadata = SessionMetadata(self.cwds.get(session_id), dict(self.envs.get(session_id, {})))
            return history_snapshot(session_id, self.active_branches.get(session_id), entries, branches, metadata)

    async def prune_branches(
        self, session_id: str, *, prefix: str, keep: Iterable[str] = (), dry_run: bool = False
    ) -> tuple[str, ...]:
        retained = validate_prune(prefix, keep)
        async with self.lock:
            if session_id not in self.active_branches:
                raise ValueError(f"session {session_id!r} not found")
            selected = prune_selection(await self.list_branches(session_id), prefix, retained)
            if not dry_run:
                for name in selected:
                    del self.branches[session_id][name]
            return selected

    async def find_session(self, name: str) -> str:
        if name in self.active_branches:
            return name
        matches = [session_id for session_id in self.active_branches if session_id.endswith(f"_{name}")]
        if not matches:
            raise ValueError(f"session {name!r} not found")
        if len(matches) > 1:
            raise ValueError(f"ambiguous session {name!r}: matches {', '.join(matches)}")
        return matches[0]

    async def delete_session(self, session_id: str) -> bool:
        async with self.lock:
            if session_id not in self.active_branches:
                return False
            for history_id in [entry.id for entry in self.entries.values() if entry.session_id == session_id]:
                del self.entries[history_id]
            del self.branches[session_id]
            del self.active_branches[session_id]
            self.cwds.pop(session_id, None)
            self.envs.pop(session_id, None)
            self.operations = {key: value for key, value in self.operations.items() if key[0] != session_id}
            return True

    async def history_dag(self, session_id: str) -> tuple[list[HistoryEntry], dict[int, list[str]]]:
        entries = sorted(
            (entry for entry in self.entries.values() if entry.session_id == session_id), key=lambda entry: entry.id
        )
        branch_map: dict[int, list[str]] = {}
        for name, history_id in self.branches.get(session_id, {}).items():
            branch_map.setdefault(history_id, []).append(name)
        return entries, branch_map
