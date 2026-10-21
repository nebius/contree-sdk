import asyncio
import inspect
import tarfile
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from contree_client.exceptions import APIConnectionError, TooEarlyError, UnprocessableEntityError
from contree_client.models import FileResponse

from contree_sdk import AsyncLazySession, ContreeAsyncSession, ContreeSession, LazySession
from contree_sdk.exceptions import FileWriteError
from contree_sdk.session import IdleSnapshotPolicy, ManualSnapshotPolicy
from tests.unit.session.lazy_clients import LiveAsyncClient, LiveClient, event
from tests.unit.session.timers import ManualTimers


async def invoke(function, *args, **kwargs):
    result = function(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def sandbox(request):
    asynchronous = request.param
    client = LiveAsyncClient() if asynchronous else LiveClient()
    base = (ContreeAsyncSession if asynchronous else ContreeSession)(client, image="base")
    lazy = (AsyncLazySession if asynchronous else LazySession)(base, snapshot_policy=ManualSnapshotPolicy())
    client.mock("ensure_file", FileResponse(uuid="uploaded", sha256="a" * 64, size=3))
    client.mock("apply_instance_file", None)
    client.mock("inspect_instance_download", b"live")
    client.mock("inspect_image_download", b"saved")
    return asynchronous, client, base, lazy


async def test_files_use_live_vm_then_selected_saved_image(sandbox):
    _, client, base, lazy = sandbox
    try:
        assert await invoke(lazy.read_file, "/file") == b"saved"
        assert not client.calls_for("spawn_instance")
        await invoke(lazy.write_file, "/file", b"live")
        assert await invoke(lazy.read_file, "/file") == b"live"
        assert lazy.phase == "running"
        assert not client.calls_for("operation_subprocess_create")
        assert not client.calls_for("operation_subprocess_stdin")
        assert len((await invoke(base.history))[0]) == 1
        await invoke(lazy.snapshot)
        assert await invoke(lazy.read_file, "/file") == b"saved"
        assert client.calls_for("inspect_image_download")[-1].args[0] == "image-op-1"
        assert len(client.calls_for("spawn_instance")) == 1
    finally:
        await invoke(lazy.abort)


@pytest.mark.parametrize("error_type", [APIConnectionError, TimeoutError, asyncio.CancelledError])
async def test_failed_native_write_is_not_retried_or_poisoned(sandbox, error_type):
    _, client, _, lazy = sandbox
    error = error_type("response lost")
    client.mocks["apply_instance_file"].clear()
    client.mock("apply_instance_file", error=error)
    try:
        with pytest.raises(error_type, match="response lost") as caught:
            await invoke(lazy.write_file, "/file", b"content")
        assert caught.value is error
        assert len(client.calls_for("apply_instance_file")) == 1
        assert lazy.state.transfers == 0
        assert lazy.error is None
        await invoke(lazy.run, "next")
        assert len(client.calls_for("spawn_instance")) == 1
    finally:
        await invoke(lazy.abort)


async def test_rejected_native_write_preserves_executor_error_contract(sandbox):
    _, client, _, lazy = sandbox
    error = UnprocessableEntityError(422, "Destination is a directory")
    client.mocks["apply_instance_file"].clear()
    client.mock("apply_instance_file", error=error)
    client.mock("apply_instance_file", None)
    try:
        with pytest.raises(FileWriteError) as caught:
            await invoke(lazy.write_file, "/directory", b"content")
        assert caught.value.path == "/directory"
        assert caught.value.message == "Destination is a directory"
        assert caught.value.__cause__ is error
        assert len(client.calls_for("apply_instance_file")) == 1
        assert lazy.state.transfers == 0
        assert lazy.error is None
        await invoke(lazy.write_file, "/good", b"content")
        assert len(client.calls_for("spawn_instance")) == 1
    finally:
        await invoke(lazy.abort)


async def test_langchain_native_upload_batch_continues_after_rejected_destination(sandbox):
    pytest.importorskip("deepagents")
    from contree_sdk.langchain import ContreeAsyncSandbox, ContreeSandbox

    asynchronous, client, _, lazy = sandbox
    client.mocks["apply_instance_file"].clear()
    client.mock("apply_instance_file", error=UnprocessableEntityError(422, "Destination is a directory"))
    client.mock("apply_instance_file", None)
    adapter = ContreeAsyncSandbox(lazy) if asynchronous else ContreeSandbox(lazy)
    upload = adapter.aupload_files if asynchronous else adapter.upload_files
    try:
        responses = await invoke(upload, [("/directory", b"bad"), ("/good", b"good")])
        assert [item.error for item in responses] == ["Destination is a directory", None]
        assert [call.args[2] for call in client.calls_for("apply_instance_file")] == ["/directory", "/good"]
        assert not client.calls_for("operation_subprocess_create")
    finally:
        await invoke(lazy.abort)


async def test_explicit_not_ready_rejection_can_retry_write(sandbox):
    _, client, _, lazy = sandbox
    client.mocks["apply_instance_file"].clear()
    client.mock("apply_instance_file", error=TooEarlyError(425, "Instance has not started"))
    client.mock("apply_instance_file", None)
    try:
        await invoke(lazy.write_file, "/file", b"content")
        assert len(client.calls_for("apply_instance_file")) == 2
        assert lazy.state.transfers == 0
    finally:
        await invoke(lazy.abort)


async def test_download_failure_preserves_existing_local_file(sandbox, tmp_path, monkeypatch):
    asynchronous, client, _, lazy = sandbox
    closed = []

    def chunks(*args):
        try:
            yield b"partial"
            raise APIConnectionError("stream disconnected")
        finally:
            closed.append(True)

    async def async_chunks(*args):
        try:
            yield b"partial"
            raise APIConnectionError("stream disconnected")
        finally:
            closed.append(True)

    monkeypatch.setattr(client, "inspect_instance_download_stream", async_chunks if asynchronous else chunks)
    target = tmp_path / "output"
    target.write_bytes(b"original")
    try:
        await invoke(lazy.run, "start")
        with pytest.raises(APIConnectionError):
            await invoke(lazy.download_file, "/file", target)
        assert target.read_bytes() == b"original"
        assert closed == [True]
        assert lazy.state.transfers == 0
        assert lazy.phase == "running"
        assert not client.calls_for("get_operation_status")
    finally:
        await invoke(lazy.abort)


async def test_upload_archive_preserves_modes_links_and_empty_dirs(sandbox, tmp_path, monkeypatch):
    asynchronous, _, base, lazy = sandbox
    source = tmp_path / "source"
    source.mkdir()
    (source / "tool").write_bytes(b"#!/bin/sh\n")
    (source / "tool").chmod(0o755)
    (source / "empty").mkdir()
    (source / "link").symlink_to("tool")
    captured = []
    upload = base.file_transfer.upload

    def capture(file):
        with tarfile.open(file.source, "r:*") as archive:
            captured.append({entry.name.removeprefix("./"): entry for entry in archive})

    def sync_upload(file):
        capture(file)
        return upload(file)

    async def async_upload(file):
        capture(file)
        return await upload(file)

    monkeypatch.setattr(base.file_transfer, "upload", async_upload if asynchronous else sync_upload)
    try:
        await invoke(lazy.upload_dir, source, "/work")
        assert captured[0]["tool"].mode & 0o111
        assert captured[0]["link"].issym()
        assert captured[0]["empty"].isdir()
    finally:
        await invoke(lazy.abort)


def test_sync_snapshot_waits_for_live_transfer_without_locking_commands(monkeypatch):
    client = LiveClient()
    started, release = threading.Event(), threading.Event()
    timers = ManualTimers()
    lazy = LazySession(
        ContreeSession(client, image="base"), snapshot_policy=IdleSnapshotPolicy(5, timer_factory=timers.start)
    )

    def read(operation, path):
        started.set()
        assert release.wait(3)
        return b"data"

    monkeypatch.setattr(client, "inspect_instance_download", read)
    lazy.run("one")
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            reading = pool.submit(lazy.read_file, "/file")
            try:
                assert started.wait(2)
                pool.submit(lazy.run, "two").result(2)
                timers.advance(100)
                assert lazy.phase == "running"
                saving = pool.submit(lazy.snapshot, timeout=2)
                with lazy.condition:
                    assert lazy.condition.wait_for(lambda: lazy.phase == "draining", 2)
                assert not client.calls_for("operation_subprocess_kill")
            finally:
                release.set()
            assert reading.result(2) == b"data"
            assert saving.result(2).image_uuid == "image-op-1"
    finally:
        lazy.abort()


async def test_async_cancelled_transfer_releases_snapshot_waiter(monkeypatch):
    client = LiveAsyncClient()
    started, release = asyncio.Event(), asyncio.Event()
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"), snapshot_policy=ManualSnapshotPolicy())

    async def read(operation, path):
        started.set()
        await release.wait()
        return b"data"

    monkeypatch.setattr(client, "inspect_instance_download", read)
    await lazy.run("one")
    reading = asyncio.create_task(lazy.read_file("/file"))
    try:
        await asyncio.wait_for(started.wait(), 2)
        await asyncio.wait_for(lazy.run("two"), 2)
        saving = asyncio.create_task(lazy.snapshot(timeout=2))
        async with lazy.condition:
            await asyncio.wait_for(lazy.condition.wait_for(lambda: lazy.phase == "draining"), 2)
        assert not client.calls_for("operation_subprocess_kill")
        reading.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reading
        assert (await saving).image_uuid == "image-op-1"
        assert lazy.state.transfers == 0
    finally:
        release.set()
        await lazy.abort()


async def test_read_after_pending_snapshot_uses_image_without_restarting_vm(sandbox):
    asynchronous, client, _, lazy = sandbox
    client.auto_exit = False
    child = await invoke(lazy.spawn, "long")
    try:
        if asynchronous:
            saving = asyncio.create_task(lazy.snapshot(timeout=2))
            async with lazy.condition:
                await asyncio.wait_for(lazy.condition.wait_for(lambda: lazy.phase == "draining"), 2)
            reading = asyncio.create_task(lazy.read_file("/file"))
            client.auto_exit = True
            await client.streams["op-1"].put(event("exit", child.spid))
            await saving
            assert await reading == b"saved"
        else:
            with ThreadPoolExecutor(max_workers=2) as pool:
                saving = pool.submit(lazy.snapshot, timeout=2)
                with lazy.condition:
                    assert lazy.condition.wait_for(lambda: lazy.phase == "draining", 2)
                reading = pool.submit(lazy.read_file, "/file")
                client.auto_exit = True
                client.streams["op-1"].put(event("exit", child.spid))
                saving.result(2)
                assert reading.result(2) == b"saved"
        assert lazy.phase == "cold"
        assert len(client.calls_for("spawn_instance")) == 1
        assert not client.calls_for("inspect_instance_download")
    finally:
        await invoke(lazy.abort)
