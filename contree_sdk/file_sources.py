"""Source records kept in a separate namespace from upload store entries."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

from contree_sdk.scope import StoreScope
from contree_sdk.store import AsyncStore, Node, SyncStore
from contree_sdk.store.ttl import Clock


SourceKind = Literal["path", "url"]
SOURCE_NAMESPACE = "file-sources"


@dataclass(frozen=True)
class FileSource:
    file_uuid: str
    sha256: str
    source: str
    kind: SourceKind
    recorded_at: float


def source_record(file_uuid: str, sha256: str, source: str, kind: SourceKind, now: float) -> FileSource:
    if not file_uuid or not source:
        raise ValueError("file UUID and source must not be empty")
    if kind not in {"path", "url"}:
        raise ValueError("source kind must be path or url")
    normalized = str(Path(source).resolve()) if kind == "path" else source
    return FileSource(file_uuid, sha256, normalized, kind, now)


class SyncFileSources:
    """Source registry backed by records with implementation-defined retention in a caller-owned store.

    Upload invalidation does not remove source records. A source is provenance,
    not proof that the remote upload still exists or that the local file is unchanged.
    """

    def __init__(self, store: SyncStore, scope: StoreScope, *, clock: Clock = time.time) -> None:
        self.store = store
        self.namespace = scope.namespace(SOURCE_NAMESPACE)
        self.clock = clock

    def record(self, file_uuid: str, sha256: str, source: str, *, kind: SourceKind = "path") -> FileSource:
        record = source_record(file_uuid, sha256, source, kind, self.clock())
        session_id = self.namespace + "/" + file_uuid
        self.store.create_session(session_id, kind="file-sources")
        self.store.append(session_id, Node(id="root", parent_id=None, kind="file", data={"uuid": file_uuid}))
        self.store.append(session_id, Node(parent_id="root", kind="source", data=asdict(record)))
        return record

    def sources(self, file_uuid: str | None = None) -> tuple[FileSource, ...]:
        session_ids = []
        cursor = None
        if file_uuid is not None:
            session_ids = [self.namespace + "/" + file_uuid]
        else:
            while True:
                page = self.store.list_sessions(kind="file-sources", prefix=self.namespace + "/", cursor=cursor)
                session_ids.extend(info.session_id for info in page.items)
                cursor = page.next_cursor
                if cursor is None:
                    break
        records = {}
        for session_id in session_ids:
            if self.store.get_session(session_id) is None:
                continue
            cursor = None
            while True:
                page = self.store.list_nodes(session_id, kind="source", cursor=cursor)
                for node in page.items:
                    record = FileSource(**cast("dict[str, Any]", node.data))
                    key = (record.file_uuid, record.kind, record.source)
                    if key not in records or record.recorded_at > records[key].recorded_at:
                        records[key] = record
                cursor = page.next_cursor
                if cursor is None:
                    break
        return tuple(records[key] for key in sorted(records))

    def forget(self, file_uuid: str) -> int:
        count = len(self.sources(file_uuid))
        self.store.delete_session(self.namespace + "/" + file_uuid)
        return count


class AsyncFileSources:
    """Source registry backed by records with implementation-defined retention in a caller-owned store.

    Upload invalidation does not remove source records. A source is provenance,
    not proof that the remote upload still exists or that the local file is unchanged.
    """

    def __init__(self, store: AsyncStore, scope: StoreScope, *, clock: Clock = time.time) -> None:
        self.store = store
        self.namespace = scope.namespace(SOURCE_NAMESPACE)
        self.clock = clock

    async def record(self, file_uuid: str, sha256: str, source: str, *, kind: SourceKind = "path") -> FileSource:
        record = source_record(file_uuid, sha256, source, kind, self.clock())
        session_id = self.namespace + "/" + file_uuid
        await self.store.create_session(session_id, kind="file-sources")
        await self.store.append(session_id, Node(id="root", parent_id=None, kind="file", data={"uuid": file_uuid}))
        await self.store.append(session_id, Node(parent_id="root", kind="source", data=asdict(record)))
        return record

    async def sources(self, file_uuid: str | None = None) -> tuple[FileSource, ...]:
        session_ids = []
        cursor = None
        if file_uuid is not None:
            session_ids = [self.namespace + "/" + file_uuid]
        else:
            while True:
                page = await self.store.list_sessions(kind="file-sources", prefix=self.namespace + "/", cursor=cursor)
                session_ids.extend(info.session_id for info in page.items)
                cursor = page.next_cursor
                if cursor is None:
                    break
        records = {}
        for session_id in session_ids:
            if await self.store.get_session(session_id) is None:
                continue
            cursor = None
            while True:
                page = await self.store.list_nodes(session_id, kind="source", cursor=cursor)
                for node in page.items:
                    record = FileSource(**cast("dict[str, Any]", node.data))
                    key = (record.file_uuid, record.kind, record.source)
                    if key not in records or record.recorded_at > records[key].recorded_at:
                        records[key] = record
                cursor = page.next_cursor
                if cursor is None:
                    break
        return tuple(records[key] for key in sorted(records))

    async def forget(self, file_uuid: str) -> int:
        count = len(await self.sources(file_uuid))
        await self.store.delete_session(self.namespace + "/" + file_uuid)
        return count
