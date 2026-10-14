"""Persistent source records, kept separately from expiring upload cache entries."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from contree_sdk.cache import AsyncCache, CacheScope, ScopedAsyncCache, ScopedSyncCache, SyncCache
from contree_sdk.cache.models import Clock


SourceKind = Literal["path", "url"]
SOURCE_NAMESPACE = "file-sources"


@dataclass(frozen=True)
class FileSource:
    file_uuid: str
    sha256: str
    source: str
    kind: SourceKind
    recorded_at: float


def source_prefix(file_uuid: str) -> str:
    return json.dumps(file_uuid) + ":"


def source_record(file_uuid: str, sha256: str, source: str, kind: SourceKind, now: float) -> tuple[str, FileSource]:
    if not file_uuid or not source:
        raise ValueError("file UUID and source must not be empty")
    if kind not in {"path", "url"}:
        raise ValueError("source kind must be path or url")
    normalized = str(Path(source).resolve()) if kind == "path" else source
    suffix = hashlib.sha256(json.dumps([kind, normalized]).encode()).hexdigest()
    return source_prefix(file_uuid) + suffix, FileSource(file_uuid, sha256, normalized, kind, now)


class SyncFileSources:
    """Source registry backed by permanent records in a caller-owned cache.

    Upload invalidation does not remove source records. A source is provenance,
    not proof that the remote upload still exists or that the local file is unchanged.
    """

    def __init__(self, cache: SyncCache, scope: CacheScope, *, clock: Clock = time.time) -> None:
        self.cache = ScopedSyncCache(cache, scope)
        self.clock = clock

    def record(self, file_uuid: str, sha256: str, source: str, *, kind: SourceKind = "path") -> FileSource:
        key, record = source_record(file_uuid, sha256, source, kind, self.clock())
        self.cache.set(key, asdict(record), namespace=SOURCE_NAMESPACE)
        return record

    def sources(self, file_uuid: str | None = None) -> tuple[FileSource, ...]:
        entries = self.cache.entries(
            namespace=SOURCE_NAMESPACE,
            prefix=source_prefix(file_uuid) if file_uuid is not None else "",
        )
        return tuple(
            sorted(
                (FileSource(**entry.value) for entry in entries),
                key=lambda item: (item.file_uuid, item.kind, item.source),
            )
        )

    def forget(self, file_uuid: str) -> int:
        return self.cache.invalidate(namespace=SOURCE_NAMESPACE, prefix=source_prefix(file_uuid))


class AsyncFileSources:
    """Source registry backed by permanent records in a caller-owned cache.

    Upload invalidation does not remove source records. A source is provenance,
    not proof that the remote upload still exists or that the local file is unchanged.
    """

    def __init__(self, cache: AsyncCache, scope: CacheScope, *, clock: Clock = time.time) -> None:
        self.cache = ScopedAsyncCache(cache, scope)
        self.clock = clock

    async def record(self, file_uuid: str, sha256: str, source: str, *, kind: SourceKind = "path") -> FileSource:
        key, record = source_record(file_uuid, sha256, source, kind, self.clock())
        await self.cache.set(key, asdict(record), namespace=SOURCE_NAMESPACE)
        return record

    async def sources(self, file_uuid: str | None = None) -> tuple[FileSource, ...]:
        entries = await self.cache.entries(
            namespace=SOURCE_NAMESPACE,
            prefix=source_prefix(file_uuid) if file_uuid is not None else "",
        )
        return tuple(
            sorted(
                (FileSource(**entry.value) for entry in entries),
                key=lambda item: (item.file_uuid, item.kind, item.source),
            )
        )

    async def forget(self, file_uuid: str) -> int:
        return await self.cache.invalidate(namespace=SOURCE_NAMESPACE, prefix=source_prefix(file_uuid))
