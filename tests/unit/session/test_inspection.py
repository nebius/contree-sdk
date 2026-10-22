import asyncio
import inspect
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
    client.mock("inspect_image_download_stream", [b"hello", b"\x00\xff"])
    client.mock("inspect_image_archive", [b"archive"])
    client.mock("check_image_file", True)
    client.mock("check_image_archive", True)
    return asynchronous, client, base, lazy


async def test_inspect_pins_all_operations_to_saved_image(setup, tmp_path):
    asynchronous, client, base, lazy = setup
    try:
        await invoke(lazy.run, "write")
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
            await invoke(lazy.read_file, "/data")
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


def test_sync_inspect_drains_commands_and_pins_before_next_vm():
    client = LiveClient()
    client.auto_exit = False
    lazy = LazySession(ContreeSession(client, image="base"), snapshot_policy=ManualSnapshotPolicy())
    handle = lazy.spawn("long")
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            reading = pool.submit(lazy.inspect, timeout=2)
            with lazy.condition:
                assert lazy.condition.wait_for(lambda: lazy.phase == "draining", 2)
            client.auto_exit = True
            next_command = pool.submit(lazy.run, "next")
            assert not client.calls_for("operation_subprocess_kill")
            client.streams["op-1"].put(event("exit", handle.spid))
            view = reading.result(2)
            next_command.result(2)
            assert view.image_uuid == "image-op-1"
            assert client.calls_for("spawn_instance")[-1].args[1] == view.image_uuid
    finally:
        lazy.abort()


async def test_async_inspect_drains_commands_and_pins_before_next_vm():
    client = LiveAsyncClient()
    client.auto_exit = False
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"), snapshot_policy=ManualSnapshotPolicy())
    handle = await lazy.spawn("long")
    try:
        reading = asyncio.create_task(lazy.inspect(timeout=2))
        async with lazy.condition:
            await asyncio.wait_for(lazy.condition.wait_for(lambda: lazy.phase == "draining"), 2)
        client.auto_exit = True
        next_command = asyncio.create_task(lazy.run("next"))
        assert not client.calls_for("operation_subprocess_kill")
        await client.streams["op-1"].put(event("exit", handle.spid))
        view = await asyncio.wait_for(reading, 2)
        await asyncio.wait_for(next_command, 2)
        assert view.image_uuid == "image-op-1"
        assert client.calls_for("spawn_instance")[-1].args[1] == view.image_uuid
    finally:
        await lazy.abort()


async def test_cancelled_inspect_does_not_cancel_snapshot_or_block_next_command():
    client = LiveAsyncClient()
    client.auto_exit = False
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"), snapshot_policy=ManualSnapshotPolicy())
    handle = await lazy.spawn("long")
    try:
        reading = asyncio.create_task(lazy.inspect())
        async with lazy.condition:
            await asyncio.wait_for(lazy.condition.wait_for(lambda: lazy.phase == "draining"), 2)
        reading.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reading
        assert not client.calls_for("cancel_operation")
        await client.streams["op-1"].put(event("exit", handle.spid))
        await lazy.snapshot(timeout=2)
        assert (await lazy.inspect()).image_uuid == "image-op-1"
    finally:
        await lazy.abort()


def test_abort_wakes_sync_inspect_waiter():
    client = LiveClient()
    client.auto_exit = False
    lazy = LazySession(ContreeSession(client, image="base"))
    lazy.spawn("long")
    with ThreadPoolExecutor(max_workers=1) as pool:
        reading = pool.submit(lazy.inspect)
        try:
            with lazy.condition:
                assert lazy.condition.wait_for(lambda: lazy.phase == "draining", 2)
            lazy.abort()
            with pytest.raises(RuntimeError, match="closed"):
                reading.result(2)
        finally:
            lazy.abort()


async def test_abort_wakes_async_inspect_waiter():
    client = LiveAsyncClient()
    client.auto_exit = False
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"))
    await lazy.spawn("long")
    reading = asyncio.create_task(lazy.inspect())
    try:
        async with lazy.condition:
            await asyncio.wait_for(lazy.condition.wait_for(lambda: lazy.phase == "draining"), 2)
        await lazy.abort()
        with pytest.raises(RuntimeError, match="closed"):
            await asyncio.wait_for(reading, 2)
    finally:
        await lazy.abort()


async def test_inspect_timeout_leaves_snapshot_running(setup):
    _, client, _, lazy = setup
    client.auto_exit = False
    try:
        await invoke(lazy.spawn, "long")
        with pytest.raises(TimeoutError, match="pending"):
            await invoke(lazy.inspect, timeout=0.001)
        assert lazy.phase == "draining"
        assert not client.calls_for("cancel_operation")
        assert not client.calls_for("inspect_image_download")
    finally:
        await invoke(lazy.abort)


def test_sync_read_pins_image_without_holding_lifecycle_lock(monkeypatch):
    import threading

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
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            reading = pool.submit(lazy.read_file, "/data")
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
    reading = asyncio.create_task(lazy.read_file("/data"))
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
