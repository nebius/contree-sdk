from __future__ import annotations

import threading
from asyncio import Lock
from datetime import datetime, timezone

from contree_sdk.store.base import AsyncStore, HistoryEntry, SyncStore


class SyncMemoryStore(SyncStore):
    """Pure in-process Store: one instance, one process's history graph."""

    def __init__(self) -> None:
        self.entries: dict[int, HistoryEntry] = {}
        self.next_id = 1
        self.branches: dict[str, dict[str, int]] = {}
        self.active_branches: dict[str, str] = {}
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
    ) -> HistoryEntry:
        with self.lock:
            branch_name = branch or self.active_branches.get(session_id) or "main"
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
            )
            self.entries[entry.id] = entry
            self.next_id += 1
            self.branches.setdefault(session_id, {})[branch_name] = entry.id
            self.active_branches.setdefault(session_id, branch_name)
            return entry

    def get_entry(self, session_id: str, history_id: int) -> HistoryEntry:
        entry = self.entries.get(history_id)
        if entry is None or entry.session_id != session_id:
            raise ValueError(f"history entry {history_id} not found in session {session_id!r}")
        return entry

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
            return True

    def history_dag(self, session_id: str) -> tuple[list[HistoryEntry], dict[int, list[str]]]:
        entries = sorted(
            (entry for entry in self.entries.values() if entry.session_id == session_id), key=lambda entry: entry.id
        )
        branch_map: dict[int, list[str]] = {}
        for name, history_id in self.branches.get(session_id, {}).items():
            branch_map.setdefault(history_id, []).append(name)
        return entries, branch_map


class AsyncMemoryStore(AsyncStore):
    """Pure in-process Store: one instance, one process's history graph."""

    def __init__(self) -> None:
        self.entries: dict[int, HistoryEntry] = {}
        self.next_id = 1
        self.branches: dict[str, dict[str, int]] = {}
        self.active_branches: dict[str, str] = {}
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
    ) -> HistoryEntry:
        async with self.lock:
            branch_name = branch or self.active_branches.get(session_id) or "main"
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
            )
            self.entries[entry.id] = entry
            self.next_id += 1
            self.branches.setdefault(session_id, {})[branch_name] = entry.id
            self.active_branches.setdefault(session_id, branch_name)
            return entry

    async def get_entry(self, session_id: str, history_id: int) -> HistoryEntry:
        entry = self.entries.get(history_id)
        if entry is None or entry.session_id != session_id:
            raise ValueError(f"history entry {history_id} not found in session {session_id!r}")
        return entry

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
            return True

    async def history_dag(self, session_id: str) -> tuple[list[HistoryEntry], dict[int, list[str]]]:
        entries = sorted(
            (entry for entry in self.entries.values() if entry.session_id == session_id), key=lambda entry: entry.id
        )
        branch_map: dict[int, list[str]] = {}
        for name, history_id in self.branches.get(session_id, {}).items():
            branch_map.setdefault(history_id, []).append(name)
        return entries, branch_map
