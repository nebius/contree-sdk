"""File trees, client streams, bounded workers, and atomic downloads."""

import asyncio
import hashlib
import threading
from pathlib import Path

import pytest
from contree_client.models import FileResponse
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk.files import (
    AsyncClientFileTransfer,
    AsyncFileTransfer,
    ClientFileTransfer,
    UploadFileSpec,
    prepare_file_tree,
)
from tests.unit.cache.test_upload_cache import call


def test_tree_permissions_exclusions_and_directory_inputs(tmp_path):
    (tmp_path / "nested").mkdir()
    script = tmp_path / "nested" / "run.sh"
    script.write_bytes(b"#!/bin/sh\ntrue\n")
    script.chmod(0o751)
    (tmp_path / "nested" / "skip.pyc").write_bytes(b"skip")
    (tmp_path / "excluded").mkdir()
    (tmp_path / "excluded" / "file").write_bytes(b"skip")
    (tmp_path / "empty").mkdir()
    prepared = prepare_file_tree(tmp_path, "/app", exclude=("*.pyc", "excluded"), uid=12, gid=34)
    assert len(prepared) == 1
    assert (str(prepared[0].path), prepared[0].uid, prepared[0].gid, prepared[0].mode) == (
        "/app/nested/run.sh",
        12,
        34,
        0o751,
    )
    overridden = prepare_file_tree(tmp_path, "/app", mode=0o600)
    assert {item.mode for item in overridden} == {0o600}
    implicit = UploadFileSpec.prepare_files({"/app": tmp_path})
    assert [str(item.path) for item in implicit] == ["/app/excluded/file", "/app/nested/run.sh", "/app/nested/skip.pyc"]
    assert next(item for item in implicit if str(item.path).endswith("run.sh")).mode == 0o751
    with pytest.raises(ValueError, match="Duplicate destination"):
        UploadFileSpec.prepare_files([*prepared, UploadFileSpec(path="/app/nested", source=b"conflict")])
    with pytest.raises(ValueError, match="Duplicate destination"):
        UploadFileSpec.prepare_files({"/app/../same": b"one", "/same": b"two"})


def test_tree_rejects_symlinks_and_missing_roots(tmp_path):
    (tmp_path / "link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        prepare_file_tree(tmp_path)
    assert prepare_file_tree(tmp_path, exclude=("link",)) == []
    with pytest.raises(ValueError, match="directory"):
        prepare_file_tree(tmp_path / "link")
    with pytest.raises(ValueError, match="directory"):
        prepare_file_tree(tmp_path / "missing")


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_upload_passes_binary_stream_and_closes_it(tmp_path, monkeypatch, asynchronous):
    path = tmp_path / "binary"
    data = bytes(range(256)) * 16384
    path.write_bytes(data)
    client = ContreeAsyncClient() if asynchronous else ContreeClient()
    handles = []
    progress = []

    def receive(content, **kwargs):
        assert not isinstance(content, bytes)
        handles.append(content)
        digest = hashlib.sha256()
        while chunk := content.read(65536):
            digest.update(chunk)
        assert digest.hexdigest() == hashlib.sha256(data).hexdigest()
        if "sha256" in kwargs:
            assert kwargs["sha256"] == digest.hexdigest()
        return FileResponse(uuid="binary", sha256=digest.hexdigest(), size=len(data))

    async def receive_async(content, **kwargs):
        return receive(content, **kwargs)

    monkeypatch.setattr(client, "ensure_file", receive_async if asynchronous else receive)
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail("whole-file read"))
    transfer = (
        AsyncClientFileTransfer(client, on_progress=progress.append)
        if isinstance(client, ContreeAsyncClient)
        else ClientFileTransfer(client, on_progress=progress.append)
    )
    spec = await call(transfer, "upload", UploadFileSpec(path="/binary", source=path))
    assert spec.uuid == "binary"
    assert handles[0].closed
    assert progress[0].bytes_transferred == len(data)


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("failure", [False, True])
async def test_streamed_download_atomic_replacement_and_cleanup(tmp_path, asynchronous, failure):
    target = tmp_path / "result"
    target.write_bytes(b"original")
    client = ContreeAsyncClient() if asynchronous else ContreeClient()
    client.mock(
        "inspect_image_download_stream", [b"a\0", b"\xffb"], error=RuntimeError("interrupted") if failure else None
    )
    progress = []
    transfer = (
        AsyncClientFileTransfer(client, on_progress=progress.append)
        if isinstance(client, ContreeAsyncClient)
        else ClientFileTransfer(client, on_progress=progress.append)
    )
    if failure:
        with pytest.raises(RuntimeError, match="interrupted"):
            await call(transfer, "download_file", "image", "/file", target)
        assert target.read_bytes() == b"original"
    else:
        assert await call(transfer, "download_file", "image", "/file", target) == 4
        assert target.read_bytes() == b"a\0\xffb"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["result"]
    assert [event.bytes_transferred for event in progress] == [2, 4]
    assert not client.calls_for("inspect_image_download")


async def test_cancelled_download_closes_stream_and_preserves_destination(tmp_path, monkeypatch):
    target = tmp_path / "result"
    target.write_bytes(b"original")
    started = asyncio.Event()
    closed = asyncio.Event()
    client = ContreeAsyncClient()

    async def stream(image, path):
        try:
            yield b"partial"
            started.set()
            await asyncio.Future()
        finally:
            closed.set()

    monkeypatch.setattr(client, "inspect_image_download_stream", stream)
    transfer = AsyncClientFileTransfer(client)
    task = asyncio.create_task(transfer.download_file("image", "/file", target))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed.is_set()
    assert target.read_bytes() == b"original"
    assert [p.name for p in tmp_path.iterdir()] == ["result"]


@pytest.mark.parametrize("cancel", [False, True])
async def test_async_upload_workers_are_bounded_and_cancelled_together(cancel):
    class Transfer(AsyncFileTransfer):
        max_concurrency = 2

        def __init__(self):
            self.started = asyncio.Event()
            self.fail = asyncio.Event()
            self.active = set()
            self.seen = []

        async def upload(self, file):
            self.active.add(file.path)
            self.seen.append(file.path)
            if len(self.active) == 2:
                self.started.set()
            try:
                await self.fail.wait()
                if str(file.path) == "/0":
                    raise RuntimeError("failed")
                await asyncio.Future()
            finally:
                self.active.remove(file.path)

        async def read_file(self, image_uuid, path):
            return b""

    transfer = Transfer()
    task = asyncio.create_task(transfer.prepare_files({f"/{n}": b"data" for n in range(20)}))
    await transfer.started.wait()
    assert len(transfer.seen) == 2
    if cancel:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        transfer.fail.set()
        with pytest.raises(RuntimeError, match="failed"):
            await task
    assert not transfer.active
    assert len(transfer.seen) == 2


def test_sync_upload_workers_are_bounded(tmp_path, monkeypatch):
    client = ContreeClient()
    lock = threading.Lock()
    barrier = threading.Barrier(2, timeout=5)
    counts = {"active": 0, "peak": 0}

    def receive(data):
        with lock:
            counts["active"] += 1
            counts["peak"] = max(counts["peak"], counts["active"])
        barrier.wait()
        with lock:
            counts["active"] -= 1
        return FileResponse(uuid="file", sha256="hash", size=4)

    monkeypatch.setattr(client, "ensure_file", receive)
    transfer = ClientFileTransfer(client, max_concurrency=2)
    result = transfer.prepare_files({f"/{n}": b"data" for n in range(6)})
    assert result is not None
    assert len(result) == 6
    assert counts == {"active": 0, "peak": 2}


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_progress_failure_preserves_download(tmp_path, asynchronous):
    target = tmp_path / "result"
    target.write_bytes(b"original")
    client = ContreeAsyncClient() if asynchronous else ContreeClient()
    client.mock("inspect_image_download_stream", [b"data"])

    def progress(event):
        raise RuntimeError("callback")

    transfer = (
        AsyncClientFileTransfer(client, on_progress=progress)
        if isinstance(client, ContreeAsyncClient)
        else ClientFileTransfer(client, on_progress=progress)
    )
    with pytest.raises(RuntimeError, match="callback"):
        await call(transfer, "download_file", "image", "/file", target)
    assert target.read_bytes() == b"original"
    assert [p.name for p in tmp_path.iterdir()] == ["result"]


async def test_async_cancel_during_hash_joins_reader_before_closing(tmp_path, monkeypatch):
    import contree_sdk.files as module

    path = tmp_path / "input"
    path.write_bytes(b"data")
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    handles = []

    def hashing(handle):
        handles.append(handle)
        loop.call_soon_threadsafe(started.set)
        release.wait(timeout=5)
        assert not handle.closed
        return hashlib.sha256(handle.read()).hexdigest()

    monkeypatch.setattr(module, "hash_upload", hashing)
    client = ContreeAsyncClient()
    task = asyncio.create_task(AsyncClientFileTransfer(client).upload(UploadFileSpec(path="/input", source=path)))
    await started.wait()
    task.cancel()
    try:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
    assert handles[0].closed
    assert not client.calls_for("ensure_file")


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_upload_failure_closes_stream(tmp_path, monkeypatch, asynchronous):
    path = tmp_path / "input"
    path.write_bytes(b"data")
    handles = []
    client = ContreeAsyncClient() if asynchronous else ContreeClient()

    def receive(handle, **kwargs):
        handles.append(handle)
        raise RuntimeError("upload")

    async def receive_async(handle, **kwargs):
        receive(handle, **kwargs)

    monkeypatch.setattr(client, "ensure_file", receive_async if asynchronous else receive)
    transfer = AsyncClientFileTransfer(client) if isinstance(client, ContreeAsyncClient) else ClientFileTransfer(client)
    with pytest.raises(RuntimeError, match="upload"):
        await call(transfer, "upload", UploadFileSpec(path="/input", source=path))
    assert handles[0].closed
