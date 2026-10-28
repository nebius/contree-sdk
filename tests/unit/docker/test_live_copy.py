"""COPY uses a live VM, preserves archive bytes, and only caches completed layers."""

import asyncio
import io
import tarfile

import pytest
from contree_client.models import DirectoryList, FileResponse

from contree_sdk.docker import ContreeAsyncDockerBuilder, ContreeDockerBuilder
from contree_sdk.exceptions import DockerBuildError
from tests.unit.docker.copy_clients import CopyAsyncClient, CopyClient, source_item


def archive_bytes():
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        directory = tarfile.TarInfo(".")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o710
        archive.addfile(directory)
        member = tarfile.TarInfo("tool")
        member.mode, member.uid, member.gid, member.size = 0o751, 1234, 2345, 4
        archive.addfile(member, io.BytesIO(b"data"))
        link = tarfile.TarInfo("link")
        link.type, link.linkname = tarfile.SYMTYPE, "tool"
        archive.addfile(link)
    return stream.getvalue()


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def live_copy(request, tmp_path, monkeypatch):
    client = CopyAsyncClient() if request.param else CopyClient()
    client.mock("check_image_archive", True)
    client.mock("check_file_exists", True)
    client.mock("inspect_image_archive", [archive_bytes()])
    client.mock("inspect_image_list", DirectoryList(path="/", files=[source_item("source", is_dir=True)]))
    client.mock("apply_instance_file", None)
    uploaded = []

    def ensure_file(content, **kwargs):
        client.record_call("ensure_file", (), kwargs)
        uploaded.append(content.read())
        return FileResponse(uuid="archive", sha256="a" * 64, size=len(uploaded[-1]))

    async def ensure_file_async(content, **kwargs):
        return ensure_file(content, **kwargs)

    monkeypatch.setattr(client, "ensure_file", ensure_file_async if request.param else ensure_file)
    (tmp_path / "Dockerfile").write_text("FROM base\nCOPY --from=source /source /target/\n")
    builder = ContreeAsyncDockerBuilder(client) if isinstance(client, CopyAsyncClient) else ContreeDockerBuilder(client)
    return client, builder, uploaded


async def build(builder, path, **kwargs):
    if isinstance(builder, ContreeAsyncDockerBuilder):
        return await builder.build(path, **kwargs)
    return await asyncio.to_thread(builder.build, path, **kwargs)


async def test_tar_bytes_live_unpack_and_signal_before_commit(live_copy, tmp_path):
    client, builder, uploaded = live_copy
    notifications = []
    assert await build(builder, tmp_path, on_event=notifications.append) == "image-op-1"
    assert uploaded == [archive_bytes()]
    spawn = client.calls_for("spawn_instance")[0]
    assert spawn.args[0] == "sleep"
    assert spawn.kwargs["args"] == ["infinity"]
    assert spawn.kwargs["files"] is ...
    assert (spawn.kwargs["uid"], spawn.kwargs["gid"]) == (0, 0)
    unpack = client.calls_for("apply_instance_file")[0]
    assert unpack.args[:2] == ("op-1", "archive")
    assert unpack.args[2] == "/target"
    assert unpack.kwargs == {"unpack": True, "replace": True, "merge": True}
    assert not client.calls_for("operation_subprocess_create")
    assert client.calls_for("operation_subprocess_kill")[-1].args == ("op-1", 1)
    assert client.calls_for("operation_subprocess_kill")[-1].kwargs == {"signal": "SIGTERM"}
    assert len(client.calls_for("follow_operation_events")) == 1
    assert notifications[-1].type == "step_completed"
    assert not client.calls_for("cancel_operation")


async def test_copy_cache_accepts_intentional_sleep_exit_and_checks_image(live_copy, tmp_path):
    client, builder, uploaded = live_copy
    first = await build(builder, tmp_path)
    assert await build(builder, tmp_path) == first
    assert len(client.calls_for("spawn_instance")) == len(uploaded) == 1
    assert len(client.calls_for("inspect_image_archive")) == 1
    assert any(call.args == (first, "/") for call in client.calls_for("check_image_archive"))


async def test_archive_reused_for_another_destination_after_head(live_copy, tmp_path):
    client, builder, uploaded = live_copy
    await build(builder, tmp_path)
    (tmp_path / "Dockerfile").write_text("FROM base\nCOPY --from=source /source /another/\n")
    assert await build(builder, tmp_path) == "image-op-2"
    assert len(uploaded) == len(client.calls_for("inspect_image_archive")) == 1
    assert client.calls_for("check_file_exists")[0].args == ("a" * 64,)


async def test_missing_uploaded_archive_is_exported_again(live_copy, tmp_path):
    client, builder, uploaded = live_copy
    await build(builder, tmp_path)
    client.mocks["check_file_exists"].clear()
    client.mock("check_file_exists", False)
    await build(builder, tmp_path, no_cache=True)
    assert len(uploaded) == len(client.calls_for("inspect_image_archive")) == 2


async def test_missing_cached_image_is_rebuilt(live_copy, tmp_path, monkeypatch):
    client, builder, uploaded = live_copy
    first = await build(builder, tmp_path)

    def exists(image, path):
        return image != first

    async def exists_async(image, path):
        return exists(image, path)

    monkeypatch.setattr(client, "check_image_archive", exists_async if isinstance(client, CopyAsyncClient) else exists)
    assert await build(builder, tmp_path) == "image-op-2"
    assert len(uploaded) == 1


@pytest.mark.parametrize("failure", ["apply", "overrides", "snapshot"])
async def test_failed_copy_is_not_committed_or_reused(live_copy, tmp_path, failure):
    client, builder, _ = live_copy
    if failure == "apply":
        client.mocks["apply_instance_file"].clear()
        client.mock("apply_instance_file", error=OSError("transfer failed"))
    elif failure == "overrides":
        (tmp_path / "Dockerfile").write_text("FROM base\nCOPY --from=source --chmod=0700 /source /target/\n")
        client.exit_code = 1
    else:
        client.wait_error = OSError("snapshot failed")
    with pytest.raises((OSError, DockerBuildError)):
        await build(builder, tmp_path)
    assert client.calls_for("cancel_operation")
    client.mocks["apply_instance_file"].clear()
    client.mock("apply_instance_file", None)
    client.exit_code = 0
    client.wait_error = None
    assert await build(builder, tmp_path) == "image-op-2"
    assert len(client.calls_for("spawn_instance")) == 2


async def test_user_workdir_overrides_and_pending_files(live_copy, tmp_path):
    client, builder, _ = live_copy
    (tmp_path / "input").write_bytes(b"input")
    (tmp_path / "Dockerfile").write_text(
        "FROM base\nUSER 1000\nWORKDIR /work\nCOPY input /pending\n"
        "COPY --from=source --chown=12:34 --chmod=0700 /source result/\n"
    )
    await build(builder, tmp_path)
    spawn = client.calls_for("spawn_instance")[0]
    assert "/pending" in spawn.kwargs["files"]
    command = client.calls_for("operation_subprocess_create")[0].args[1]
    assert "chown -h 12:34" in command
    assert "chmod 700" in command
    assert "/work/result" in command
    assert builder.ctx.user == "1000"
    assert not builder.ctx.pending


async def test_async_cancellation_cancels_vm_and_does_not_commit(live_copy, tmp_path, monkeypatch):
    client, builder, _ = live_copy
    if not isinstance(client, CopyAsyncClient):
        pytest.skip("async cancellation")
    started = asyncio.Event()

    async def apply(*args, **kwargs):
        started.set()
        await asyncio.Future()

    monkeypatch.setattr(client, "apply_instance_file", apply)
    task = asyncio.create_task(build(builder, tmp_path))
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client.calls_for("cancel_operation")
    assert builder.ctx.last_image == "base"


@pytest.mark.parametrize("overrides", [False, True])
async def test_regular_file_uses_raw_attachment_and_file_spec(live_copy, tmp_path, overrides):
    client, builder, uploaded = live_copy
    client.mocks["inspect_image_list"].clear()
    client.mock("inspect_image_list", DirectoryList(path="/", files=[source_item("tool")]))
    client.mock("inspect_image_download_stream", [b"binary\x00data"])
    flags = "--chown=12:34 --chmod=0700 " if overrides else ""
    (tmp_path / "Dockerfile").write_text(f"FROM base\nCOPY --from=source {flags}/tool /renamed\n")
    first = await build(builder, tmp_path)
    assert uploaded == [b"binary\x00data"]
    assert not client.calls_for("inspect_image_archive")
    assert not client.calls_for("apply_instance_file")
    assert not client.calls_for("operation_subprocess_create")
    file = client.calls_for("spawn_instance")[0].kwargs["files"]["/renamed"]
    assert (file.uid, file.gid, file.mode) == ((12, 34, "0700") if overrides else (1234, 2345, "0751"))
    assert await build(builder, tmp_path) == first
    assert len(uploaded) == len(client.calls_for("spawn_instance")) == 1
    (tmp_path / "Dockerfile").write_text(f"FROM base\nCOPY --from=source {flags}/tool /elsewhere\n")
    await build(builder, tmp_path)
    assert len(uploaded) == len(client.calls_for("inspect_image_download_stream")) == 1
    assert "/elsewhere" in client.calls_for("spawn_instance")[-1].kwargs["files"]


async def test_overrides_run_after_unpack_before_stop_and_only_touch_archive_entries(live_copy, tmp_path):
    client, builder, _ = live_copy
    (tmp_path / "Dockerfile").write_text("FROM base\nCOPY --from=source --chmod=0700 --chown=12:34 /source /target\n")
    await build(builder, tmp_path)
    command = client.calls_for("operation_subprocess_create")[0].args[1]
    assert "chmod 700 /target/tool" in command
    assert "chown -h 12:34 /target/link" in command
    assert "chmod 700 /target/link" not in command
    assert " -R " not in command
    calls = [call.operation for call in client.calls]
    assert calls.index("apply_instance_file") < calls.index("operation_subprocess_create")
    assert calls.index("operation_subprocess") < calls.index("operation_subprocess_kill")


@pytest.mark.parametrize("directory_first", [False, True])
async def test_mixed_sources_keep_copy_order(live_copy, tmp_path, directory_first):
    client, builder, _ = live_copy
    client.mocks["inspect_image_list"].clear()
    client.mock(
        "inspect_image_list", DirectoryList(path="/", files=[source_item("source", is_dir=True), source_item("tool")])
    )
    client.mock("inspect_image_download_stream", [b"last"])
    sources = "/source /tool" if directory_first else "/tool /source"
    (tmp_path / "Dockerfile").write_text(f"FROM base\nCOPY --from=source {sources} /target/\n")
    await build(builder, tmp_path)
    spawns = client.calls_for("spawn_instance")
    assert len(spawns) == (2 if directory_first else 1)
    assert "/target/tool" in spawns[-1].kwargs["files"]
    if directory_first:
        assert spawns[0].kwargs["files"] is ...
    assert client.calls_for("apply_instance_file")[0].args[2] == "/target"


async def test_symlink_file_source_uses_target_bytes_and_metadata(live_copy, tmp_path):
    from dataclasses import replace

    client, builder, uploaded = live_copy
    client.mocks["inspect_image_list"].clear()
    link = replace(source_item("link"), is_regular=False, is_symlink=True, symlink_to="tool", mode=0o777)
    client.mock("inspect_image_list", DirectoryList(path="/", files=[link, source_item("tool", mode=0o751)]))
    client.mock("inspect_image_download_stream", [b"data"])
    (tmp_path / "Dockerfile").write_text("FROM base\nCOPY --from=source /link /result/\n")
    await build(builder, tmp_path)
    assert uploaded == [b"data"]
    assert client.calls_for("inspect_image_download_stream")[0].args == ("base", "/tool")
    assert client.calls_for("spawn_instance")[0].kwargs["files"]["/result/link"].mode == "0751"
