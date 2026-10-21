import asyncio
import inspect
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import aclosing, closing

import pytest
from contree_client.models import DirectoryList, GrepResult, Image, OperationStatus

from contree_sdk import AsyncLazySession, ContreeAsyncSession, ContreeSession, LazySession
from contree_sdk.session import AbstractSnapshotPolicy
from tests.unit.session.lazy_clients import LiveAsyncClient, LiveClient, event


class ManualSnapshotPolicy(AbstractSnapshotPolicy):
    def notify(self, event):
        super().notify(event)


async def invoke(function, *args, **kwargs):
    result = function(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def setup(request):
    asynchronous = request.param
    client: LiveAsyncClient | LiveClient
    base: ContreeAsyncSession | ContreeSession
    lazy: AsyncLazySession | LazySession
    if asynchronous:
        client = LiveAsyncClient()
        base = ContreeAsyncSession(client, image="base")
        lazy = AsyncLazySession(base, snapshot_policy=ManualSnapshotPolicy())
    else:
        client = LiveClient()
        base = ContreeSession(client, image="base")
        lazy = LazySession(base, snapshot_policy=ManualSnapshotPolicy())
    client.mock("inspect_image", Image(uuid="saved"))
    client.mock("inspect_image_list", DirectoryList(path="/", files=[]))
    client.mock("inspect_image_grep", GrepResult(path="/", patterns=["hello"], matches=[], truncated=False))
    client.mock("inspect_image_download", b"hello\x00\xff")
    client.mock("inspect_instance_download", b"live")
    client.mock("inspect_image_download_stream", [b"hello", b"\x00\xff"])
    client.mock("inspect_image_archive", [b"archive"])
    client.mock("check_image_file", True)
    client.mock("check_image_archive", True)
    return asynchronous, client, base, lazy


async def test_inspect_pins_all_operations_to_saved_image(setup, tmp_path):
    asynchronous, client, base, lazy = setup
    try:
        await invoke(lazy.run, "write")
        await invoke(lazy.snapshot)
        view = await invoke(lazy.inspect)
        assert view.image_uuid == "image-op-1"
        assert lazy.phase == "cold"
        await invoke(lazy.run, "change")
        assert (await invoke(view.info)).uuid == "saved"
        assert (await invoke(view.list, "/")).files == []
        options = {
            "path": ["/etc", "/work"],
            "glob": ["*.txt"],
            "max_count": 4,
            "max_total": 8,
            "case": "smart",
            "before": 1,
            "after": 2,
        }
        assert (await invoke(view.grep, ["hello", "world"], **options)).matches == []
        assert client.calls_for("inspect_image_grep")[0].kwargs == options
        assert await invoke(view.read_file, "/data") == b"hello\x00\xff"
        target = tmp_path / "download"
        assert await invoke(view.download_file, "/data", target) == 7
        assert target.read_bytes() == b"hello\x00\xff"
        assert await invoke(view.file_exists, "/data")
        assert await invoke(view.archive_exists, "/work")
        if asynchronous:
            async with aclosing(view.iter_file("/data")) as chunks:
                assert b"".join([chunk async for chunk in chunks]) == b"hello\x00\xff"
            async with aclosing(view.archive("/work", compressed=True)) as chunks:
                assert b"".join([chunk async for chunk in chunks]) == b"archive"
        else:
            with closing(view.iter_file("/data")) as chunks:
                assert b"".join(chunks) == b"hello\x00\xff"
            with closing(view.archive("/work", compressed=True)) as chunks:
                assert b"".join(chunks) == b"archive"
        for call in client.calls:
            if call.operation.startswith(("inspect_", "check_image_")):
                assert call.args[0] == "image-op-1"
        assert client.calls_for("inspect_image_archive")[0].kwargs == {"compressed": True}
        assert len(client.calls_for("spawn_instance")) == 2
        assert len(client.calls_for("get_operation_status")) == 1
    finally:
        await invoke(lazy.abort)


async def test_cold_read_and_branch_changes_need_no_vm(setup):
    _, client, base, lazy = setup
    try:
        assert (await invoke(lazy.inspect)).image_uuid == "base"
        assert await invoke(lazy.read_file, "/data") == b"hello\x00\xff"
        assert not client.calls_for("spawn_instance")
        await invoke(lazy.run, "one")
        assert await invoke(lazy.read_file, "/data") == b"live"
        assert lazy.phase == "running"
        assert client.calls_for("inspect_instance_download")[-1].args[0] == "op-1"
        await invoke(lazy.snapshot)
        assert await invoke(lazy.read_file, "/data") == b"hello\x00\xff"
        assert client.calls_for("inspect_image_download")[-1].args[0] == "image-op-1"
        await invoke(lazy.rollback)
        assert (await invoke(lazy.inspect)).image_uuid == "base"
        assert len(client.calls_for("spawn_instance")) == 1
        direct = await invoke(base.inspect)
        assert direct.image_uuid == "base"
    finally:
        await invoke(lazy.close)
    with pytest.raises(RuntimeError, match="closed"):
        await invoke(lazy.inspect)


@pytest.mark.parametrize("failure", ["missing_image", "failed", "wait", "store"])
async def test_failed_snapshot_does_not_inspect_stale_image(setup, failure, monkeypatch):
    _, client, base, lazy = setup
    try:
        await invoke(lazy.run, "write")
        if failure == "missing_image":
            client.result_image = False
        elif failure == "failed":
            client.final_status = OperationStatus.FAILED
        elif failure == "wait":
            client.wait_error = OSError("snapshot failed")
        else:

            def fail(*args, **kwargs):
                raise OSError("store unavailable")

            monkeypatch.setattr(base.store, "append", fail)
        with pytest.raises(RuntimeError):
            await invoke(lazy.snapshot)
        with pytest.raises(RuntimeError, match="failed"):
            await invoke(lazy.inspect)
        assert not client.calls_for("inspect_image_download")
        assert base.image_uuid == "base"
        assert lazy.error is not None
    finally:
        await invoke(lazy.abort)


async def test_inspect_error_does_not_poison_saved_session(setup):
    _, client, _, lazy = setup
    client.mocks["inspect_image_list"].clear()
    client.mock("inspect_image_list", error=OSError("inspect failed"))
    try:
        await invoke(lazy.run, "write")
        await invoke(lazy.snapshot)
        view = await invoke(lazy.inspect)
        with pytest.raises(OSError, match="inspect failed"):
            await invoke(view.list)
        assert lazy.error is None
        await invoke(lazy.run, "next")
        assert client.calls_for("spawn_instance")[-1].args[1] == view.image_uuid
    finally:
        await invoke(lazy.close)


async def test_partial_streams_close_source(setup, monkeypatch):
    asynchronous, client, _, lazy = setup
    closed = []

    def source(*args, **kwargs):
        try:
            yield b"one"
            yield b"two"
        finally:
            closed.append(args[0])

    async def async_source(*args, **kwargs):
        try:
            yield b"one"
            yield b"two"
        finally:
            closed.append(args[0])

    callback = async_source if asynchronous else source
    monkeypatch.setattr(client, "inspect_image_archive", callback)
    monkeypatch.setattr(client, "inspect_image_download_stream", callback)
    try:
        view = await invoke(lazy.inspect)
        for method in [view.archive, view.iter_file]:
            if asynchronous:
                async with aclosing(method("/data")) as chunks:
                    assert await anext(chunks) == b"one"
            else:
                with closing(method("/data")) as chunks:
                    assert next(chunks) == b"one"
        assert closed == ["base", "base"]
    finally:
        await invoke(lazy.close)


async def test_inspect_rejects_running_vm_without_stopping_it(setup):
    _, client, _, lazy = setup
    client.auto_exit = False
    try:
        handle = await invoke(lazy.spawn, "long")
        with pytest.raises(RuntimeError, match=r"Live inspection.*snapshot"):
            await invoke(lazy.inspect)
        assert lazy.phase == "running"
        assert handle.spid in lazy.state.active
        assert lazy.error is None
        assert not client.calls_for("operation_subprocess_kill")
        assert not client.calls_for("get_operation_status")
        assert not client.calls_for("cancel_operation")
        assert not client.calls_for("inspect_image")
    finally:
        await invoke(lazy.abort)


async def test_inspect_rejects_draining_vm_without_waiting_or_cancelling_snapshot(setup):
    asynchronous, client, _, lazy = setup
    client.auto_exit = False
    try:
        handle = await invoke(lazy.spawn, "long")
        with pytest.raises(TimeoutError, match="pending"):
            await invoke(lazy.snapshot, timeout=0.001)
        assert lazy.phase == "draining"
        with pytest.raises(RuntimeError, match="Live inspection"):
            await invoke(lazy.inspect)
        assert lazy.phase == "draining"
        assert lazy.error is None
        assert not client.calls_for("operation_subprocess_kill")
        assert not client.calls_for("cancel_operation")
        if asynchronous:
            await client.streams["op-1"].put(event("exit", handle.spid))
        else:
            client.streams["op-1"].put(event("exit", handle.spid))
        await invoke(lazy.snapshot, timeout=2)
        assert (await invoke(lazy.inspect)).image_uuid == "image-op-1"
    finally:
        await invoke(lazy.abort)


async def test_inspect_rejects_snapshot_in_progress_without_inspecting_old_image(setup):
    asynchronous, client, _, lazy = setup
    client.wait_gate = asyncio.Event() if asynchronous else threading.Event()
    await invoke(lazy.run, "write")
    saving = asyncio.create_task(
        lazy.snapshot(timeout=2) if asynchronous else asyncio.to_thread(lazy.snapshot, timeout=2)
    )
    try:
        if asynchronous:
            await asyncio.wait_for(client.saving.wait(), 2)
        else:
            assert await asyncio.to_thread(client.saving.wait, 2)
        assert lazy.phase == "snapshotting"
        with pytest.raises(RuntimeError, match="Live inspection"):
            await invoke(lazy.inspect)
        assert lazy.phase == "snapshotting"
        assert lazy.error is None
        assert not client.calls_for("inspect_image")
        assert not client.calls_for("cancel_operation")
    finally:
        client.wait_gate.set()
        await saving
        await invoke(lazy.abort)


def test_sync_read_pins_image_without_holding_lifecycle_lock(monkeypatch):
    client = LiveClient()
    base = ContreeSession(client, image="base")
    started, release = threading.Event(), threading.Event()
    images = []

    def read(image_uuid, path):
        images.append(image_uuid)
        started.set()
        assert release.wait(2)
        return b"saved"

    monkeypatch.setattr(base.file_transfer, "read_file", read)
    lazy = LazySession(base, snapshot_policy=ManualSnapshotPolicy())
    lazy.run("one")
    lazy.snapshot()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            reading = pool.submit(lambda: lazy.inspect().read_file("/data"))
            try:
                assert started.wait(2)
                pool.submit(lazy.run, "two").result(2)
                assert client.calls_for("spawn_instance")[-1].args[1] == "image-op-1"
            finally:
                release.set()
            assert reading.result(2) == b"saved"
        assert images == ["image-op-1"]
    finally:
        lazy.abort()


async def test_async_read_pins_image_without_holding_lifecycle_lock(monkeypatch):
    client = LiveAsyncClient()
    base = ContreeAsyncSession(client, image="base")
    started, release = asyncio.Event(), asyncio.Event()
    images = []

    async def read(image_uuid, path):
        images.append(image_uuid)
        started.set()
        await release.wait()
        return b"saved"

    monkeypatch.setattr(base.file_transfer, "read_file", read)
    lazy = AsyncLazySession(base, snapshot_policy=ManualSnapshotPolicy())
    await lazy.run("one")
    await lazy.snapshot()

    async def read_saved():
        view = await lazy.inspect()
        return await view.read_file("/data")

    reading = asyncio.create_task(read_saved())
    try:
        await asyncio.wait_for(started.wait(), 2)
        await asyncio.wait_for(lazy.run("two"), 2)
        assert client.calls_for("spawn_instance")[-1].args[1] == "image-op-1"
        release.set()
        assert await asyncio.wait_for(reading, 2) == b"saved"
        assert images == ["image-op-1"]
    finally:
        release.set()
        await reading
        await lazy.abort()
