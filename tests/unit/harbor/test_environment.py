import asyncio
import io
import logging
import tarfile
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from contree_client.exceptions import ConflictError, TooEarlyError
from contree_client.models import FileResponse, StreamRepr


pytest.importorskip("harbor")

from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.config import EnvironmentConfig
from harbor.models.trial.paths import TrialPaths
from tests.unit.session.lazy_clients import LiveAsyncClient

from contree_sdk.harbor import ConTreeEnvironment


@pytest.fixture
def backend(tmp_path, monkeypatch):
    client = LiveAsyncClient()
    client.mock("ensure_file", FileResponse(uuid="uploaded", sha256="a" * 64, size=4))
    client.mock("apply_instance_file", None)
    monkeypatch.setattr("contree_sdk.harbor.environment.async_import_image", AsyncMock(return_value="base"))
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir()
    env = ConTreeEnvironment(
        environment_dir=environment_dir,
        environment_name="test",
        session_id="test__env",
        trial_paths=TrialPaths(trial_dir=tmp_path / "trial"),
        task_env_config=EnvironmentConfig(docker_image="alpine:latest"),
        contree_client=client,
    )
    return client, env


def test_harbor_factory(backend):
    _, environment = backend
    created = EnvironmentFactory.create_environment_from_import_path(
        "contree_sdk.harbor:ConTreeEnvironment",
        environment_dir=environment.environment_dir,
        environment_name="test",
        session_id="factory",
        trial_paths=environment.trial_paths,
        task_env_config=environment.task_env_config,
        contree_client=environment._contree_client,
    )
    assert isinstance(created, ConTreeEnvironment)
    assert not any(created.capabilities.model_dump().values())


async def test_vm_persists_across_exec_and_file_transfers(backend, tmp_path, monkeypatch, caplog):
    client, env = backend
    caplog.set_level(logging.DEBUG, logger=env.logger.name)
    uploaded = []

    async def ensure_file(source, **kwargs):
        uploaded.append(source.read())
        return FileResponse(uuid="uploaded", sha256="a" * 64, size=len(uploaded[-1]))

    monkeypatch.setattr(client, "ensure_file", ensure_file)
    upload_source = tmp_path / "upload"
    nested = upload_source / "nested"
    nested.mkdir(parents=True)
    (nested / "data.bin").write_bytes(b"\x00\xffpayload")
    await env.start(force_build=False)
    assert (await env.exec("printf hello")).return_code == 0
    source = tmp_path / "source.txt"
    source.write_bytes(b"\x00\xffhello")
    await env.upload_file(source, "/app/source.txt")
    await env.upload_dir(upload_source, "/work")
    assert len(client.calls_for("apply_instance_file")) == 2
    assert {call.args[2] for call in client.calls_for("apply_instance_file")} == {
        "/app/source.txt",
        "/work/nested/data.bin",
    }
    assert uploaded == [b"\x00\xffhello", b"\x00\xffpayload"]
    assert (await env.exec("after transfers")).return_code == 0
    assert len(client.calls_for("spawn_instance")) == 1
    await env.stop(delete=True)
    assert "upload_file source=" in caplog.text
    assert "upload_dir source=" in caplog.text
    assert "stop finished elapsed_sec=" in caplog.text


async def test_debug_logs_identify_snapshot_resume_without_command_contents(backend, caplog):
    client, env = backend
    env._snapshot_idle_sec = 0.02
    caplog.set_level(logging.DEBUG, logger=env.logger.name)
    await env.start(force_build=False)
    try:
        await asyncio.wait_for(client.saving.wait(), 1)
        await env._require_lazy().snapshot(timeout=1)
        await env.exec("printf secret-command", env={"TOKEN": "secret-env"})
        records = [record for record in caplog.records if record.name == env.logger.name]
        messages = [record.getMessage() for record in records]
        assert all(record.levelno == logging.DEBUG for record in records)
        assert all(datetime.fromisoformat(message.split()[0]).utcoffset() == timedelta(0) for message in messages)
        assert any(
            "phase=cold operation=None" in message and "snapshot_operation=op-1" in message for message in messages
        )
        assert any("operation=op-2" in message and "snapshot_image=image-op-1" in message for message in messages)
        assert "exec result return_code=0" in caplog.text
        assert "secret-command" not in caplog.text
        assert "secret-env" not in caplog.text
    finally:
        await env.stop()


async def test_start_uploads_task_environment_into_workdir(backend, monkeypatch):
    client, env = backend
    env.task_env_config.workdir = "/workspace"
    (env.environment_dir / "settings.json").write_bytes(b'{"answer": 42}')
    uploaded = []

    async def ensure_file(source, **kwargs):
        uploaded.append(source.read())
        return FileResponse(uuid="uploaded", sha256="a" * 64, size=len(uploaded[-1]))

    monkeypatch.setattr(client, "ensure_file", ensure_file)
    await env.start(force_build=False)
    assert uploaded == [b'{"answer": 42}']
    assert any(call.args[2] == "/workspace/settings.json" for call in client.calls_for("apply_instance_file"))
    assert (await env.exec("true")).return_code == 0
    await env.stop()


@pytest.mark.parametrize("delete", [None, False], ids=["default", "no-delete"])
async def test_stop_aborts_without_saving_for_either_delete_value(backend, delete):
    client, env = backend
    await env.start(force_build=False)
    await env.exec("true")
    if delete is None:
        await env.stop()
    else:
        await env.stop(delete=delete)
    assert len(client.calls_for("cancel_operation")) == 1
    assert not client.calls_for("get_operation_status")
    with pytest.raises(RuntimeError, match="not running"):
        await env.exec("true")
    await env.stop()
    assert len(client.calls_for("cancel_operation")) == 1


async def test_stop_aborts_vm_during_an_active_command(backend):
    client, env = backend
    await env.start(force_build=False)
    client.auto_exit = False
    client.created.clear()
    running = asyncio.create_task(env.exec("sleep 100"))
    await asyncio.wait_for(client.created.wait(), 1)

    await env.stop()

    with pytest.raises(RuntimeError):
        await asyncio.wait_for(running, 1)
    assert client.calls_for("cancel_operation")
    with pytest.raises(RuntimeError, match="not running"):
        await env.exec("true")


async def test_stop_succeeds_when_cancel_does_not_end_event_stream(backend, monkeypatch):
    client, env = backend
    client.stream_timeout = None

    async def cancel_without_events(operation_id):
        client.record_call("cancel_operation", (operation_id,), {})

    monkeypatch.setattr(client, "cancel_operation", cancel_without_events)
    await env.start(force_build=False)
    assert (await env.exec("true")).return_code == 0

    await asyncio.wait_for(env.stop(), 12)

    assert len(client.calls_for("cancel_operation")) == 1
    with pytest.raises(RuntimeError, match="not running"):
        await env.exec("true")
    await env.stop()


async def test_stop_failure_allows_restart(backend, monkeypatch):
    client, env = backend
    await env.start(force_build=False)
    cancel = client.cancel_operation

    async def fail_cancel(operation_id):
        await cancel(operation_id)
        raise OSError("cancel failed")

    monkeypatch.setattr(client, "cancel_operation", fail_cancel)
    with pytest.raises(OSError, match="cancel failed"):
        await env.stop()
    monkeypatch.setattr(client, "cancel_operation", cancel)
    await env.start(force_build=False)
    assert (await env.exec("true")).return_code == 0
    await env.stop()


async def test_exec_timeout_allows_next_command_in_same_vm(backend, caplog):
    client, env = backend
    caplog.set_level(logging.DEBUG, logger=env.logger.name)
    await env.start(force_build=False)
    client.auto_exit = False
    with pytest.raises(TimeoutError):
        await env.exec("sleep 100", timeout_sec=0.02)
    client.auto_exit = True
    assert (await env.exec("true")).return_code == 0
    assert len(client.calls_for("spawn_instance")) == 1
    await env.stop(delete=True)
    assert any(
        "exec failed elapsed_sec=" in record.getMessage() and "error_type=TimeoutError" in record.getMessage()
        for record in caplog.records
    )


async def test_invalid_config_and_paths(backend, tmp_path):
    _, env = backend
    await env.start(force_build=False)
    try:
        with pytest.raises(ValueError, match="absolute"):
            await env.upload_file(tmp_path / "missing", "relative")
    finally:
        await env.stop()
    with pytest.raises(ValueError, match="switching users"):
        await env.exec("id", user="nobody")
    with pytest.raises(ValueError, match="positive"):
        ConTreeEnvironment(
            environment_dir=env.environment_dir,
            environment_name="test",
            session_id="bad",
            trial_paths=env.trial_paths,
            task_env_config=env.task_env_config,
            snapshot_idle_sec=0,
        )


async def test_start_imports_oci_image(backend):
    client, env = backend
    import contree_sdk.harbor.environment as module

    try:
        await env.start(force_build=False)
        assert isinstance(module.async_import_image, AsyncMock)
        module.async_import_image.assert_awaited_once()
        assert module.async_import_image.await_args.args == ("alpine:latest",)
        assert client.calls_for("spawn_instance")[0].args[1] == "base"
    finally:
        await env.stop()


@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_failed_start_aborts_vm_and_preserves_startup_error(backend, monkeypatch, cleanup_fails):
    client, env = backend
    execute = env._execute
    startup_error = ValueError("startup check failed")

    async def fail_start(*args, **kwargs):
        await execute(*args, **kwargs)
        raise startup_error

    monkeypatch.setattr(env, "_execute", fail_start)
    if cleanup_fails:
        cancel = client.cancel_operation

        async def fail_cancel(operation_id):
            await cancel(operation_id)
            raise OSError("cleanup failed")

        monkeypatch.setattr(client, "cancel_operation", fail_cancel)
    try:
        with pytest.raises(ValueError, match="startup check failed") as error:
            await env.start(force_build=False)
        assert error.value is startup_error
        assert len(client.calls_for("cancel_operation")) == 1
        with pytest.raises(RuntimeError, match="not running"):
            await env.exec("true")
    finally:
        await env.stop()


async def test_start_succeeds_after_transient_readiness_rejections(backend, monkeypatch):
    client, env = backend
    create = client.operation_subprocess_create
    attempts = 0

    async def not_ready_then_create(operation_id, command, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ConflictError(409, "Operation is PENDING, not running")
        if attempts == 2:
            raise TooEarlyError(425, f"control channel not connected for operation {operation_id}")
        return await create(operation_id, command, **kwargs)

    monkeypatch.setattr(client, "operation_subprocess_create", not_ready_then_create)
    await env.start(force_build=False)
    assert (await env.exec("true")).return_code == 0
    await env.stop(delete=True)


async def test_download_file_preserves_binary_data_and_allows_exec(backend, tmp_path, monkeypatch):
    client, env = backend
    await env.start(force_build=False)
    payload = b"\x00" + b"x" * (256 * 1024 + 17)

    async def downloaded_chunks(operation_id, path):
        yield payload[: 256 * 1024]
        yield payload[256 * 1024 :]

    monkeypatch.setattr(client, "inspect_instance_download_stream", downloaded_chunks)
    target = tmp_path / "download.bin"
    await env.download_file("/remote/data.bin", target)
    assert target.read_bytes() == payload
    assert (await env.exec("true")).return_code == 0
    await env.stop(delete=True)


async def test_download_dir_merges_nested_files_and_empty_directories(backend, tmp_path, monkeypatch):
    client, env = backend
    await env.start(force_build=False)
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        content = b"log contents\n"
        member = tarfile.TarInfo("nested/log.txt")
        member.size = len(content)
        tar.addfile(member, io.BytesIO(content))
        empty = tarfile.TarInfo("empty/")
        empty.type = tarfile.DIRTYPE
        tar.addfile(empty)

    async def archived(operation_id, path, **kwargs):
        payload = archive.getvalue()
        yield payload[:100]
        yield payload[100:]

    monkeypatch.setattr(client, "inspect_instance_archive", archived)
    destination = tmp_path / "logs"
    destination.mkdir()
    (destination / "existing.txt").write_text("keep")
    (destination / "nested").mkdir()
    (destination / "nested/log.txt").write_text("old")
    try:
        await env.download_dir("/remote/logs", destination)
        assert (destination / "nested/log.txt").read_bytes() == b"log contents\n"
        assert (destination / "existing.txt").read_text() == "keep"
        assert (destination / "empty").is_dir()
        assert (await env.exec("true")).return_code == 0
    finally:
        await env.stop()


async def test_download_dir_rejects_unsafe_archive_member(backend, tmp_path, monkeypatch):
    client, env = backend
    await env.start(force_build=False)
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        content = b"outside"
        member = tarfile.TarInfo("../outside.txt")
        member.size = len(content)
        tar.addfile(member, io.BytesIO(content))

    async def archived(*args, **kwargs):
        yield archive.getvalue()

    monkeypatch.setattr(client, "inspect_instance_archive", archived)
    try:
        with pytest.raises(tarfile.FilterError):
            await env.download_dir("/remote/logs", tmp_path / "logs")
        assert not (tmp_path / "outside.txt").exists()
    finally:
        await env.stop()


@pytest.mark.parametrize(
    ("cwd", "user", "uid"),
    [(None, None, ...), ("/override", "root", 0), ("/override", 1000, 1000)],
)
async def test_exec_forwards_harbor_options_and_converts_the_result(backend, monkeypatch, cwd, user, uid):
    client, env = backend
    env.task_env_config.workdir = "/default"
    env._persistent_env = {"BASE": "persistent", "SHARED": "persistent"}
    await env.start(force_build=False)
    get_result = client.result_for_command
    client.exit_code = 7

    def completed(command):
        result = get_result(command)
        result.stdout = StreamRepr.from_bytes(b"output\xff")
        result.stderr = StreamRepr.from_text("error")
        return result

    monkeypatch.setattr(client, "result_for_command", completed)
    try:
        with env.scoped_exec_env({"SHARED": "scoped"}):
            result = await env.exec("echo example", cwd=cwd, env={"SHARED": "command"}, timeout_sec=1, user=user)
        call = client.calls_for("operation_subprocess_create")[-1]
        assert call.kwargs["cwd"] == (cwd or "/default")
        assert call.kwargs["env"] == {"BASE": "persistent", "SHARED": "scoped"}
        assert call.kwargs["uid"] == uid
        assert result.return_code == 7
        assert result.stdout == "output�"
        assert result.stderr == "error"
    finally:
        await env.stop()


async def test_exec_cancellation_allows_next_command(backend):
    client, env = backend
    await env.start(force_build=False)
    client.auto_exit = False
    client.created.clear()
    running = asyncio.create_task(env.exec("sleep 100"))
    try:
        await asyncio.wait_for(client.created.wait(), 1)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(running, 1)
        client.auto_exit = True
        assert (await env.exec("next")).return_code == 0
    finally:
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)
        await env.stop()
