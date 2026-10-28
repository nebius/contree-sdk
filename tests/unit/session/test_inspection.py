import asyncio
import inspect
from concurrent.futures import ThreadPoolExecutor
from contextlib import aclosing, closing

import pytest
from contree_client.exceptions import UnprocessableEntityError
from contree_client.models import DirectoryList, FileResponse, GrepResult, Image, OperationStatus

from contree_sdk import AsyncLazySession, ContreeAsyncSession, ContreeSession, LazySession
from contree_sdk.exceptions import FileWriteError
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
    client.mock("inspect_instance_list", DirectoryList(path="/", files=[]))
    client.mock("inspect_instance_grep", GrepResult(path="/", patterns=["hello"], matches=[], truncated=False))
    client.mock("inspect_instance_download", b"live\x00\xff")
    client.mock("inspect_instance_download_stream", [b"live", b"\x00\xff"])
    client.mock("inspect_instance_archive", [b"live-archive"])
    client.mock("check_instance_file", True)
    client.mock("check_instance_archive", True)
    return asynchronous, client, base, lazy


async def test_inspect_pins_all_operations_to_saved_image(setup, tmp_path):
    asynchronous, client, base, lazy = setup
    try:
        await invoke(lazy.run, "write")
        view = await invoke(lazy.inspect_snapshot)
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
        assert (await invoke(lazy.inspect_snapshot)).image_uuid == "base"
        assert await invoke((await invoke(lazy.inspect_snapshot)).read_file, "/data") == b"hello\x00\xff"
        assert not client.calls_for("spawn_instance")
        await invoke(lazy.run, "one")
        assert await invoke((await invoke(lazy.inspect_snapshot)).read_file, "/data") == b"hello\x00\xff"
        assert client.calls_for("inspect_image_download")[-1].args[0] == "image-op-1"
        await invoke(lazy.rollback)
        assert (await invoke(lazy.inspect_snapshot)).image_uuid == "base"
        assert len(client.calls_for("spawn_instance")) == 1
        direct = await invoke(base.inspect)
        assert direct.image_uuid == "base"
    finally:
        await invoke(lazy.close)
    with pytest.raises(RuntimeError, match="closed"):
        await invoke(lazy.inspect_snapshot)


async def test_large_live_write_uses_file_transfer_without_subprocess_stdin(setup):
    _, client, _, lazy = setup
    client.mock("ensure_file", FileResponse(uuid="uploaded", sha256="a" * 64, size=2 * 1024 * 1024))
    client.mock("apply_instance_file", None)
    try:
        await invoke(lazy.write_file, "/large.bin", b"x" * (2 * 1024 * 1024))
        assert len(client.calls_for("ensure_file")) == 1
        assert client.calls_for("apply_instance_file")[0].args[:3] == ("op-1", "uploaded", "/large.bin")
        assert not client.calls_for("operation_subprocess_create")
        assert not client.calls_for("operation_subprocess_stdin")
    finally:
        await invoke(lazy.abort)


async def test_rejected_live_write_preserves_session_for_next_upload(setup):
    _, client, _, lazy = setup
    client.mock("ensure_file", FileResponse(uuid="uploaded", sha256="a" * 64, size=3))
    client.mock("ensure_file", FileResponse(uuid="uploaded", sha256="a" * 64, size=3))
    client.mock("apply_instance_file", error=UnprocessableEntityError(422, "Destination is a directory"))
    client.mock("apply_instance_file", None)
    try:
        with pytest.raises(FileWriteError, match="Destination is a directory"):
            await invoke(lazy.write_file, "/directory", b"bad")
        assert lazy.error is None
        await invoke(lazy.write_file, "/good", b"ok")
        assert len(client.calls_for("spawn_instance")) == 1
        assert not client.calls_for("operation_subprocess_create")
    finally:
        await invoke(lazy.abort)


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
            await invoke((await invoke(lazy.inspect_snapshot)).read_file, "/data")
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
        view = await invoke(lazy.inspect_snapshot)
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
        view = await invoke(lazy.inspect_snapshot)
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
            reading = pool.submit(lazy.inspect_snapshot, timeout=2)
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
        reading = asyncio.create_task(lazy.inspect_snapshot(timeout=2))
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
        reading = asyncio.create_task(lazy.inspect_snapshot())
        async with lazy.condition:
            await asyncio.wait_for(lazy.condition.wait_for(lambda: lazy.phase == "draining"), 2)
        reading.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reading
        assert not client.calls_for("cancel_operation")
        await client.streams["op-1"].put(event("exit", handle.spid))
        await lazy.snapshot(timeout=2)
        assert (await lazy.inspect_snapshot()).image_uuid == "image-op-1"
    finally:
        await lazy.abort()


def test_abort_wakes_sync_inspect_waiter():
    client = LiveClient()
    client.auto_exit = False
    lazy = LazySession(ContreeSession(client, image="base"))
    lazy.spawn("long")
    with ThreadPoolExecutor(max_workers=1) as pool:
        reading = pool.submit(lazy.inspect_snapshot)
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
    reading = asyncio.create_task(lazy.inspect_snapshot())
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
            await invoke(lazy.inspect_snapshot, timeout=0.001)
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
            reading = pool.submit(lazy.inspect_snapshot().read_file, "/data")
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
    reading = asyncio.create_task((await lazy.inspect_snapshot()).read_file("/data"))
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


async def test_live_inspection_reuses_vm_for_all_file_operations(setup, tmp_path):
    asynchronous, client, base, lazy = setup
    try:
        await invoke(lazy.run, "write")
        view = await invoke(lazy.inspect)
        assert lazy.phase == "running"
        assert (await invoke(view.list)).files == []
        options = {
            "path": ["/work", "/etc"],
            "glob": "*.txt",
            "max_count": 3,
            "max_total": 7,
            "case": "smart",
            "before": 1,
            "after": 2,
        }
        assert (await invoke(view.grep, ["hello", "world"], **options)).matches == []
        assert client.calls_for("inspect_instance_grep")[0].kwargs == options
        assert await invoke(lazy.read_file, "/data") == b"live\x00\xff"
        target = tmp_path / "download"
        assert await invoke(view.download_file, "/data", target) == 6
        assert target.read_bytes() == b"live\x00\xff"
        assert await invoke(view.file_exists, "/data")
        assert await invoke(view.archive_exists, "/work")
        if asynchronous:
            async with aclosing(view.iter_file("/data")) as chunks:
                assert b"".join([chunk async for chunk in chunks]) == b"live\x00\xff"
            async with aclosing(view.archive("/work", compressed=True)) as chunks:
                assert b"".join([chunk async for chunk in chunks]) == b"live-archive"
        else:
            with closing(view.iter_file("/data")) as chunks:
                assert b"".join(chunks) == b"live\x00\xff"
            with closing(view.archive("/work", compressed=True)) as chunks:
                assert b"".join(chunks) == b"live-archive"
        await invoke(lazy.run, "next")
        assert client.calls_for("inspect_instance_archive")[0].kwargs == {"compressed": True}
        assert not client.calls_for("operation_subprocess_kill")
        assert not client.calls_for("get_operation_status")
        assert len(client.calls_for("spawn_instance")) == 1
        assert base.image_uuid == "base"
        for call in client.calls:
            if call.operation.startswith(("inspect_", "check_")):
                assert call.args[0] == "op-1"
    finally:
        await invoke(lazy.close)


async def test_view_selects_current_source_at_request_time(setup):
    _, client, _, lazy = setup
    try:
        view = await invoke(lazy.inspect)
        assert await invoke(view.read_file, "/data") == b"hello\x00\xff"
        assert not client.calls_for("spawn_instance")
        await invoke(lazy.run, "write")
        assert await invoke(view.read_file, "/data") == b"live\x00\xff"
        await invoke(lazy.snapshot)
        assert await invoke(view.read_file, "/data") == b"hello\x00\xff"
        assert client.calls_for("inspect_image_download")[-1].args[0] == "image-op-1"
        await invoke(lazy.run, "change")
        assert await invoke(view.read_file, "/data") == b"live\x00\xff"
        assert client.calls_for("inspect_instance_download")[-1].args[0] == "op-2"
    finally:
        await invoke(lazy.close)
    with pytest.raises(RuntimeError, match="closed"):
        await invoke(view.read_file, "/data")


@pytest.mark.parametrize("method", ["iter_file", "archive"])
@pytest.mark.parametrize("finish", ["snapshot", "close"])
async def test_live_stream_delays_snapshot_until_closed(setup, monkeypatch, method, finish):
    asynchronous, client, _, lazy = setup
    released = []

    def source(*args, **kwargs):
        try:
            yield b"first"
            yield b"second"
        finally:
            released.append(True)

    async def async_source(*args, **kwargs):
        try:
            yield b"first"
            yield b"second"
        finally:
            released.append(True)

    endpoint = "inspect_instance_download_stream" if method == "iter_file" else "inspect_instance_archive"
    monkeypatch.setattr(client, endpoint, async_source if asynchronous else source)
    try:
        await invoke(lazy.run, "write")
        view = await invoke(lazy.inspect)
        chunks = getattr(view, method)("/data")
        assert (await anext(chunks) if asynchronous else next(chunks)) == b"first"
        assert lazy.state.inspecting == 1
        with pytest.raises(TimeoutError, match="pending"):
            await invoke(getattr(lazy, finish), timeout=0.001)
        assert lazy.phase == "draining"
        assert not client.calls_for("operation_subprocess_kill")
        if asynchronous:
            await chunks.aclose()
        else:
            chunks.close()
        await invoke(getattr(lazy, finish), timeout=2)
        assert lazy.state.inspecting == 0
        assert released == [True]
        assert len(client.calls_for("operation_subprocess_kill")) == 1
    finally:
        await invoke(lazy.abort)


@pytest.mark.parametrize(
    ("endpoint", "method"),
    [
        ("inspect_instance_list", "list"),
        ("inspect_instance_download", "read_file"),
        ("inspect_instance_grep", "grep"),
        ("check_instance_file", "file_exists"),
        ("check_instance_archive", "archive_exists"),
    ],
)
async def test_live_error_has_no_image_fallback_and_releases_admission(setup, endpoint, method):
    _, client, _, lazy = setup
    client.mocks[endpoint].clear()
    client.mock(endpoint, error=OSError("live inspection failed"))
    try:
        await invoke(lazy.run, "write")
        view = await invoke(lazy.inspect)
        with pytest.raises(OSError, match="live inspection failed"):
            await invoke(getattr(view, method), "/data")
        assert lazy.state.inspecting == 0
        assert lazy.error is None
        assert not any("image" in call.operation and call.operation.startswith("inspect") for call in client.calls)
        await invoke(lazy.run, "next")
        assert len(client.calls_for("spawn_instance")) == 1
    finally:
        await invoke(lazy.close)


async def test_live_download_failure_preserves_destination(setup, tmp_path, monkeypatch):
    asynchronous, client, _, lazy = setup
    target = tmp_path / "data"
    target.write_bytes(b"original")
    closed = []

    def source(*args, **kwargs):
        try:
            yield b"partial"
            raise OSError("connection lost")
        finally:
            closed.append(True)

    async def async_source(*args, **kwargs):
        try:
            yield b"partial"
            raise OSError("connection lost")
        finally:
            closed.append(True)

    monkeypatch.setattr(client, "inspect_instance_download_stream", async_source if asynchronous else source)
    try:
        await invoke(lazy.run, "write")
        view = await invoke(lazy.inspect)
        with pytest.raises(OSError, match="connection lost"):
            await invoke(view.download_file, "/data", target)
        assert target.read_bytes() == b"original"
        assert list(tmp_path.iterdir()) == [target]
        assert closed == [True]
        assert lazy.state.inspecting == 0
    finally:
        await invoke(lazy.close)


async def test_cold_staging_is_applied_before_inspection(setup, monkeypatch):
    from contree_sdk.files import UploadedFile, UploadFileSpec

    _, client, base, lazy = setup
    spawn = client.spawn_instance

    def sync_spawn(*args, **kwargs):
        response = spawn(*args, **kwargs)
        client.streams[response.uuid].put(event("spawn"))
        return response

    async def async_spawn(*args, **kwargs):
        response = await spawn(*args, **kwargs)
        await client.streams[response.uuid].put(event("spawn"))
        return response

    monkeypatch.setattr(client, "spawn_instance", async_spawn if setup[0] else sync_spawn)
    try:
        await invoke(
            base.stage_files, [UploadFileSpec(path="/input", source=UploadedFile(uuid="uploaded", sha256="a" * 64))]
        )
        assert await invoke(lazy.read_file, "/input") == b"live\x00\xff"
        assert lazy.phase == "running"
        assert not client.calls_for("inspect_image_download")
        assert not client.calls_for("operation_subprocess_create")
        assert "/input" in client.calls_for("spawn_instance")[0].kwargs["files"]
        await invoke(lazy.snapshot)
        assert not await invoke(base.pending_files)
    finally:
        await invoke(lazy.abort)


def test_sync_live_read_allows_commands_and_delays_snapshot(monkeypatch):
    import threading

    client = LiveClient()
    lazy = LazySession(ContreeSession(client, image="base"), snapshot_policy=ManualSnapshotPolicy())
    started, release = threading.Event(), threading.Event()

    def read(operation_uuid, path):
        assert operation_uuid == "op-1"
        started.set()
        assert release.wait(3)
        return b"live"

    monkeypatch.setattr(client, "inspect_instance_download", read)
    lazy.run("one")
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            reading = pool.submit(lazy.read_file, "/data")
            try:
                assert started.wait(2)
                pool.submit(lazy.run, "two").result(2)
                assert len(client.calls_for("spawn_instance")) == 1
                with pytest.raises(TimeoutError):
                    lazy.snapshot(timeout=0.001)
                assert not client.calls_for("operation_subprocess_kill")
            finally:
                release.set()
            assert reading.result(2) == b"live"
        lazy.snapshot(timeout=2)
        assert lazy.state.inspecting == 0
    finally:
        release.set()
        lazy.abort()


async def test_async_live_read_cancellation_releases_snapshot(monkeypatch):
    client = LiveAsyncClient()
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"), snapshot_policy=ManualSnapshotPolicy())
    started = asyncio.Event()

    async def read(operation_uuid, path):
        assert operation_uuid == "op-1"
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(client, "inspect_instance_download", read)
    await lazy.run("one")
    reading = asyncio.create_task(lazy.read_file("/data"))
    try:
        await asyncio.wait_for(started.wait(), 2)
        await asyncio.wait_for(lazy.run("two"), 2)
        assert len(client.calls_for("spawn_instance")) == 1
        with pytest.raises(TimeoutError):
            await lazy.snapshot(timeout=0.001)
        assert not client.calls_for("operation_subprocess_kill")
        reading.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reading
        assert lazy.state.inspecting == 0
        await lazy.snapshot(timeout=2)
    finally:
        reading.cancel()
        await lazy.abort()


async def test_inspection_waiting_for_snapshot_uses_saved_image(setup):
    _, client, _, lazy = setup
    client.auto_exit = False
    try:
        handle = await invoke(lazy.spawn, "long")
        with pytest.raises(TimeoutError):
            await invoke(lazy.snapshot, timeout=0.001)
        view = await invoke(lazy.inspect, timeout=0.001)
        with pytest.raises(TimeoutError, match="admission"):
            await invoke(view.read_file, "/data")
        assert lazy.error is None
        assert not client.calls_for("inspect_instance_download")
        await invoke(client.streams["op-1"].put, event("exit", handle.spid))
        await invoke(lazy.snapshot, timeout=2)
        assert await invoke(view.read_file, "/data") == b"hello\x00\xff"
        assert client.calls_for("inspect_image_download")[-1].args[0] == "image-op-1"
    finally:
        await invoke(lazy.abort)


async def test_live_inspection_counts_as_idle_activity_not_a_command(setup):
    from contree_sdk.session import CommandCountSnapshotPolicy, CompositeSnapshotPolicy, IdleSnapshotPolicy
    from tests.unit.session.timers import ManualTimers

    asynchronous, client, _, lazy = setup
    timers = ManualTimers()
    idle = IdleSnapshotPolicy(5, timer_factory=timers.start)
    count = CommandCountSnapshotPolicy(3)
    lazy.snapshot_policy = CompositeSnapshotPolicy(idle, count)
    try:
        await invoke(lazy.run, "one")
        timers.advance(4)
        view = await invoke(lazy.inspect)
        chunks = view.iter_file("/data")
        assert (await anext(chunks) if asynchronous else next(chunks)) == b"live"
        timers.advance(10)
        assert not idle.future.done()
        assert count.commands_started == 1
        assert not client.calls_for("operation_subprocess_kill")
        if asynchronous:
            await chunks.aclose()
        else:
            chunks.close()
        timers.advance(4)
        assert not idle.future.done()
        timers.advance(1)
        assert idle.future.done()
        await invoke(lazy.snapshot, timeout=2)
        assert lazy.phase == "cold"
    finally:
        await invoke(lazy.abort)


async def test_cancelled_stream_cleanup_holds_reservation_through_repeated_cancel(monkeypatch):
    client = LiveAsyncClient()
    lazy = AsyncLazySession(ContreeAsyncSession(client, image="base"), snapshot_policy=ManualSnapshotPolicy())
    started, cleanup, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def stream(*args, **kwargs):
        try:
            yield b"prefix"
            started.set()
            await asyncio.Event().wait()
        finally:
            cleanup.set()
            await release.wait()

    monkeypatch.setattr(client, "inspect_instance_download_stream", stream)
    await lazy.run("one")
    view = await lazy.inspect()

    async def consume():
        async with aclosing(view.iter_file("/data")) as chunks:
            async for _ in chunks:
                pass

    reading = asyncio.create_task(consume())
    try:
        await asyncio.wait_for(started.wait(), 2)
        reading.cancel()
        await asyncio.wait_for(cleanup.wait(), 2)
        reading.cancel()
        await asyncio.sleep(0)
        assert lazy.state.inspecting == 1
        assert not client.calls_for("operation_subprocess_kill")
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await reading
        assert lazy.state.inspecting == 0
    finally:
        release.set()
        await lazy.abort()
