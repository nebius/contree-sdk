"""Upload reuse and source provenance through real client-backed transfers."""

import asyncio
import hashlib
import inspect
from dataclasses import replace
from pathlib import Path

import pytest
from contree_client.models import FileResponse
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk.cache import AsyncCache, AsyncSQLiteCache, CacheScope, SyncSQLiteCache
from contree_sdk.file_sources import AsyncFileSources, SyncFileSources
from contree_sdk.files import AsyncClientFileTransfer, ClientFileTransfer, UploadedFile, UploadFileSpec
from contree_sdk.upload_cache import AsyncCachedFileTransfer, CachedFileTransfer


async def call(obj, method, *args, **kwargs):
    value = getattr(obj, method)(*args, **kwargs)
    return await value if inspect.isawaitable(value) else value


def components(cache, *, endpoint="https://one.invalid", ttl=10):
    if isinstance(cache, AsyncCache):
        client = ContreeAsyncClient(base_url=endpoint)
        client.mock("ensure_file", FileResponse(uuid="upload", sha256="a" * 64, size=4))
        return client, AsyncCachedFileTransfer(
            AsyncClientFileTransfer(client), cache, scope=CacheScope.from_client(client), ttl=ttl
        )
    client = ContreeClient(base_url=endpoint)
    client.mock("ensure_file", FileResponse(uuid="upload", sha256="a" * 64, size=4))
    return client, CachedFileTransfer(ClientFileTransfer(client), cache, scope=CacheScope.from_client(client), ttl=ttl)


async def test_reuse_content_expiry_permissions_and_sources(cache_case, tmp_path):
    cache, now = cache_case
    client, transfer = components(cache)
    path = tmp_path / "input"
    path.write_bytes(b"same")
    file = UploadFileSpec(path="/input", source=path)
    first = await call(transfer, "upload", file)
    now[0] += 9
    second = await call(transfer, "upload", replace(file, uid=42, gid=43, mode="0600"))
    assert first.uuid == second.uuid == "upload"
    assert (second.uid, second.gid, second.mode) == (42, 43, "0600")
    other = tmp_path / "other"
    other.write_bytes(b"same")
    await call(transfer, "upload", replace(file, source=other))
    assert len(client.calls_for("ensure_file")) == 1
    records = await call(transfer.sources, "sources", "upload")
    assert {r.source for r in records} == {str(path), str(other)}
    assert {r.sha256 for r in records} == {hashlib.sha256(b"same").hexdigest()}
    now[0] += 1
    await call(transfer, "upload", file)
    assert len(client.calls_for("ensure_file")) == 2
    path.write_bytes(b"diff")  # Same length; content determines the fingerprint.
    await call(transfer, "upload", file)
    assert len(client.calls_for("ensure_file")) == 3
    assert await call(transfer.cache, "invalidate", namespace="uploads") == 2
    assert len(await call(transfer.sources, "sources")) == 2
    await call(transfer, "upload", file)
    assert len(client.calls_for("ensure_file")) == 4
    foreign_client, foreign = components(cache, endpoint="https://two.invalid")
    await call(foreign, "upload", file)
    assert len(foreign_client.calls_for("ensure_file")) == 1
    assert await call(foreign.sources, "forget", "upload") == 1
    assert len(await call(transfer.sources, "sources")) == 2


async def test_bytes_uploaded_references_and_reads(cache_case):
    cache, _ = cache_case
    client, transfer = components(cache)
    client.mock("inspect_image_download", b"download")
    spec = UploadFileSpec(path="/data", source=b"same")
    await call(transfer, "upload", spec)
    await call(transfer, "upload", spec)
    result = await call(transfer, "upload", replace(spec, source=UploadedFile(uuid="existing", sha256="hash")))
    assert result.uuid == "existing"
    assert len(client.calls_for("ensure_file")) == 1
    assert await call(transfer.sources, "sources") == ()
    assert await call(transfer, "read_file", "image", "/data") == b"download"
    assert await call(transfer, "read_stdin", b"stdin") == b"stdin"


async def test_snapshot_is_stable_and_removed_on_success_or_failure(cache_case, tmp_path, monkeypatch):
    cache, _ = cache_case
    _, transfer = components(cache)
    source = tmp_path / "original"
    source.write_bytes(b"before")
    observed = []
    original = transfer.transfer.upload

    def inspect_upload(file):
        observed.append(Path(file.source))
        source.write_bytes(b"after")
        assert Path(file.source).read_bytes() == b"before"

    if isinstance(cache, AsyncCache):

        async def upload(file):
            inspect_upload(file)
            return await original(file)

    else:

        def upload(file):
            inspect_upload(file)
            return original(file)

    monkeypatch.setattr(transfer.transfer, "upload", upload)
    await call(transfer, "upload", UploadFileSpec(path="/data", source=source))
    assert not observed[0].exists()
    assert (await call(transfer.cache, "entries", namespace="uploads"))[0].key == hashlib.sha256(b"before").hexdigest()

    def fail(file):
        observed.append(Path(file.source))
        raise RuntimeError("upload failed")

    monkeypatch.setattr(transfer.transfer, "upload", fail)
    with pytest.raises(RuntimeError, match="upload failed"):
        await call(transfer, "upload", UploadFileSpec(path="/data", source=source))
    assert not observed[-1].exists()
    assert len(await call(transfer.cache, "entries", namespace="uploads")) == 1


async def test_sources_survive_sqlite_reopen_and_separate_uuid_prefixes(tmp_path):
    path = tmp_path / "cache.db"
    scope = CacheScope.from_client(ContreeClient())
    with SyncSQLiteCache(path) as cache:
        sources = SyncFileSources(cache, scope)
        sources.record("a", "hash", "https://example.invalid/file", kind="url")
        sources.record("ab", "hash", str(tmp_path / "local"))
    async with AsyncSQLiteCache(path) as cache:
        sources = AsyncFileSources(cache, scope)
        assert len(await sources.sources("a")) == 1
        assert (await sources.sources("a"))[0].kind == "url"
        assert await sources.forget("a") == 1
        assert [s.file_uuid for s in await sources.sources()] == ["ab"]


async def test_cancelled_upload_removes_snapshot(tmp_path, monkeypatch):
    from contree_sdk.cache import AsyncMemoryCache

    client, transfer = components(AsyncMemoryCache())
    source = tmp_path / "original"
    source.write_bytes(b"data")
    started = asyncio.Event()
    paths = []

    async def upload(file):
        paths.append(Path(file.source))
        started.set()
        await asyncio.Future()

    monkeypatch.setattr(transfer.transfer, "upload", upload)
    task = asyncio.create_task(transfer.upload(UploadFileSpec(path="/data", source=source)))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not paths[0].exists()
    assert await transfer.cache.entries(namespace="uploads") == ()
    assert not client.calls_for("ensure_file")


async def test_cancelled_snapshot_copy_is_joined_and_cleaned(tmp_path, monkeypatch):
    import threading

    import contree_sdk.upload_cache as module
    from contree_sdk.cache import AsyncMemoryCache

    _, transfer = components(AsyncMemoryCache())
    source = tmp_path / "original"
    source.write_bytes(b"data")
    original = module.snapshot_upload
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    snapshots = []

    def snapshot(file):
        result = original(file)
        snapshots.append(result)
        loop.call_soon_threadsafe(started.set)
        release.wait(timeout=5)
        return result

    monkeypatch.setattr(module, "snapshot_upload", snapshot)
    task = asyncio.create_task(transfer.upload(UploadFileSpec(path="/data", source=source)))
    await started.wait()
    task.cancel()
    try:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
    assert not Path(snapshots[0].file.source).exists()
    assert await transfer.cache.entries(namespace="uploads") == ()
