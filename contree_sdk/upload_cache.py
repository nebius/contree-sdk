"""Opt-in upload reuse through the public file-transfer and cache contracts."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import TemporaryDirectory

from contree_client.models import FileSpec

from contree_sdk.cache import AsyncCache, CacheScope, ScopedAsyncCache, ScopedSyncCache, SyncCache
from contree_sdk.cache.models import expiration
from contree_sdk.file_sources import AsyncFileSources, SyncFileSources
from contree_sdk.files import AsyncFileTransfer, InputSource, SyncFileTransfer, UploadedFile, UploadFileSpec


UPLOAD_NAMESPACE = "uploads"
COPY_CHUNK_SIZE = 1024 * 1024


@dataclass
class UploadSnapshot:
    file: UploadFileSpec
    sha256: str
    source: str | None = None
    directory: TemporaryDirectory[str] | None = None

    def close(self) -> None:
        if self.directory is not None:
            self.directory.cleanup()


def snapshot_upload(file: UploadFileSpec) -> UploadSnapshot:
    if isinstance(file.source, bytes):
        return UploadSnapshot(file, hashlib.sha256(file.source).hexdigest())
    if isinstance(file.source, UploadedFile):
        raise TypeError("uploaded references do not need a snapshot")
    source = Path(file.source).resolve()
    directory = TemporaryDirectory(prefix="contree-upload-")
    path = Path(directory.name) / "content"
    digest = hashlib.sha256()
    try:
        with source.open("rb") as input_file, path.open("wb") as output_file:
            while chunk := input_file.read(COPY_CHUNK_SIZE):
                digest.update(chunk)
                output_file.write(chunk)
        return UploadSnapshot(replace(file, source=path), digest.hexdigest(), str(source), directory)
    except BaseException:
        directory.cleanup()
        raise


@contextmanager
def upload_snapshot(file: UploadFileSpec) -> Iterator[UploadSnapshot]:
    snapshot = snapshot_upload(file)
    try:
        yield snapshot
    finally:
        snapshot.close()


@asynccontextmanager
async def async_upload_snapshot(file: UploadFileSpec) -> AsyncIterator[UploadSnapshot]:
    task = asyncio.create_task(asyncio.to_thread(snapshot_upload, file))
    try:
        snapshot = await asyncio.shield(task)
    except asyncio.CancelledError as cancelled:
        try:
            snapshot = await task
        except BaseException:
            raise cancelled from None
        await asyncio.to_thread(snapshot.close)
        raise
    try:
        yield snapshot
    finally:
        await asyncio.to_thread(snapshot.close)


def cached_uuid(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    uuid = value.get("uuid")
    return uuid if isinstance(uuid, str) and uuid else None


def attachment(uuid: str, file: UploadFileSpec) -> FileSpec:
    return FileSpec(uuid=uuid, uid=file.uid, gid=file.gid, mode=file.mode)


class CachedFileTransfer(SyncFileTransfer):
    """Cache content uploads; apply permissions from each current request.

    ttl is required and measured from upload completion. Hits do not renew it.
    Concurrent misses may upload the same content. The caller owns all components.
    """

    def __init__(
        self,
        transfer: SyncFileTransfer,
        cache: SyncCache,
        *,
        scope: CacheScope,
        ttl: float,
        sources: SyncFileSources | None = None,
    ) -> None:
        expiration(ttl, 0)
        self.transfer = transfer
        self.cache = ScopedSyncCache(cache, scope)
        self.ttl = ttl
        self.sources = sources if sources is not None else SyncFileSources(cache, scope)

    def upload(self, file: UploadFileSpec) -> FileSpec:
        if isinstance(file.source, UploadedFile):
            return self.transfer.upload(file)
        with upload_snapshot(file) as snapshot:
            uuid = cached_uuid(self.cache.get(snapshot.sha256, namespace=UPLOAD_NAMESPACE))
            if uuid is None:
                result = self.transfer.upload(snapshot.file)
                uuid = result.uuid
                if uuid is Ellipsis or not uuid:
                    raise ValueError("upload returned no file UUID")
                self.cache.set(snapshot.sha256, {"uuid": uuid}, namespace=UPLOAD_NAMESPACE, ttl=self.ttl)
            if snapshot.source is not None:
                self.sources.record(uuid, snapshot.sha256, snapshot.source)
            return attachment(uuid, file)

    def read_file(self, image_uuid: str, path: str) -> bytes:
        return self.transfer.read_file(image_uuid, path)

    def read_stdin(self, source: InputSource) -> str | bytes:
        return self.transfer.read_stdin(source)


class AsyncCachedFileTransfer(AsyncFileTransfer):
    """Cache content uploads; apply permissions from each current request.

    ttl is required and measured from upload completion. Hits do not renew it.
    Concurrent misses may upload the same content. The caller owns all components.
    """

    def __init__(
        self,
        transfer: AsyncFileTransfer,
        cache: AsyncCache,
        *,
        scope: CacheScope,
        ttl: float,
        sources: AsyncFileSources | None = None,
    ) -> None:
        expiration(ttl, 0)
        self.transfer = transfer
        self.cache = ScopedAsyncCache(cache, scope)
        self.ttl = ttl
        self.sources = sources if sources is not None else AsyncFileSources(cache, scope)

    async def upload(self, file: UploadFileSpec) -> FileSpec:
        if isinstance(file.source, UploadedFile):
            return await self.transfer.upload(file)
        async with async_upload_snapshot(file) as snapshot:
            uuid = cached_uuid(await self.cache.get(snapshot.sha256, namespace=UPLOAD_NAMESPACE))
            if uuid is None:
                result = await self.transfer.upload(snapshot.file)
                uuid = result.uuid
                if uuid is Ellipsis or not uuid:
                    raise ValueError("upload returned no file UUID")
                await self.cache.set(snapshot.sha256, {"uuid": uuid}, namespace=UPLOAD_NAMESPACE, ttl=self.ttl)
            if snapshot.source is not None:
                await self.sources.record(uuid, snapshot.sha256, snapshot.source)
            return attachment(uuid, file)

    async def read_file(self, image_uuid: str, path: str) -> bytes:
        return await self.transfer.read_file(image_uuid, path)

    async def read_stdin(self, source: InputSource) -> str | bytes:
        return await self.transfer.read_stdin(source)
