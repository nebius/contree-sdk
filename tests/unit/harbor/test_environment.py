import asyncio
import io
import tarfile
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
        client=client,
        snapshot_timeout=2,
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
        client=environment._client,
    )
    assert isinstance(created, ConTreeEnvironment)
    assert not any(created.capabilities.model_dump().values())


async def test_vm_persists_across_exec_and_file_transfers(backend, tmp_path, monkeypatch):
    client, env = backend
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
    assert len(client.calls_for("spawn_instance")) == 1
    assert client.calls_for("spawn_instance")[0].kwargs["timeout"] == 3600
    result = await env.exec("printf hello")
    assert result.return_code == 0
    assert len(client.calls_for("spawn_instance")) == 1
    source = tmp_path / "source.txt"
    source.write_bytes(b"\x00\xffhello")
    await env.upload_file(source, "/app/source.txt")
    await env.upload_dir(upload_source, "/work")
    assert len(client.calls_for("spawn_instance")) == 1
    assert len(client.calls_for("apply_instance_file")) == 2
    assert {call.args[2] for call in client.calls_for("apply_instance_file")} == {
        "/app/source.txt",
        "/work/nested/data.bin",
    }
    assert all(call.kwargs["replace"] for call in client.calls_for("apply_instance_file"))
    assert [call.args[1] for call in client.calls_for("operation_subprocess_create")][-2:] == ["true", "true"]
    assert uploaded == [b"\x00\xffhello", b"\x00\xffpayload"]
    assert not client.calls_for("operation_subprocess_stdin")
    await env.stop(delete=True)
    assert client.calls_for("cancel_operation")
    assert not client.calls_for("get_operation_status")


async def test_session_snapshot_restarts_from_saved_image(backend):
    client, env = backend
    await env.start(force_build=False)
    first_operation = client.calls_for("spawn_instance")[0].args[1]
    await env.exec("true")
    entry = await env._lazy_session.snapshot(timeout=2)
    assert entry.image_uuid == "image-op-1"
    await env.exec("true")
    starts = client.calls_for("spawn_instance")
    assert [start.args[1] for start in starts] == [first_operation, entry.image_uuid]
    await env.stop(delete=True)


@pytest.mark.parametrize(
    "stop_kwargs", [{}, {"delete": True}, {"delete": False}], ids=["default", "delete", "no-delete"]
)
async def test_stop_aborts_without_saving_for_either_delete_value(backend, stop_kwargs):
    client, env = backend
    await env.start(force_build=False)
    await env.exec("true")
    session = env._lazy_session
    await env.stop(**stop_kwargs)
    assert session.phase == "closed"
    assert session.last_entry is None
    assert session.session.image_uuid == "base"
    assert len(client.calls_for("cancel_operation")) == 1
    assert not client.calls_for("update_image_tag")
    assert env._lazy_session is None
    assert env._lazy_session_context is None
    assert env._client is client
    assert not client.calls_for("get_operation_status")
    await env.stop(**stop_kwargs)
    assert len(client.calls_for("cancel_operation")) == 1


async def test_stop_aborts_vm_during_an_active_command(backend):
    client, env = backend
    await env.start(force_build=False)
    client.auto_exit = False
    client.created.clear()
    running = asyncio.create_task(env.exec("sleep 100"))
    await asyncio.wait_for(client.created.wait(), 1)

    await env.stop()

    await asyncio.wait_for(running, 1)
    assert client.calls_for("cancel_operation")
    assert env._lazy_session is None


async def test_failed_abort_releases_context(backend, monkeypatch):
    client, env = backend
    await env.start(force_build=False)
    session = env._lazy_session
    abort = session.abort

    async def fail_after_abort():
        await abort()
        raise OSError("abort failed")

    monkeypatch.setattr(session, "abort", fail_after_abort)
    with pytest.raises(OSError, match="abort failed"):
        await env.stop()
    assert session.phase == "closed"
    assert session.last_entry is None
    assert client.calls_for("cancel_operation")
    assert not client.calls_for("update_image_tag")
    assert env._lazy_session is None
    assert env._lazy_session_context is None
    assert env._client is client


async def test_timeout_kills_child_and_reuses_vm(backend):
    client, env = backend
    await env.start(force_build=False)
    client.auto_exit = False
    with pytest.raises(TimeoutError):
        await env.exec("sleep 100", timeout_sec=0.02)
    assert client.calls_for("operation_subprocess_kill")[-1].args == ("op-1", client.processes)
    client.auto_exit = True
    await env.exec("true")
    assert len(client.calls_for("spawn_instance")) == 1
    await env.stop(delete=True)


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


async def test_environment_uses_public_sandbox_factory(backend, monkeypatch):
    client, env = backend
    import contree_sdk.harbor.environment as module
    from contree_sdk import AsyncLazySession, ContreeAsyncSession

    calls = []
    factory = module.create_async_sandbox_session

    def capture(**kwargs):
        calls.append(kwargs)
        return factory(**kwargs)

    monkeypatch.setattr(module, "create_async_sandbox_session", capture)
    await env.start(force_build=False)
    assert len(calls) == 1
    assert calls[0]["client"] is client
    assert calls[0]["session_kwargs"]["vm_request"].timeout_seconds == env._vm_timeout
    assert type(env._lazy_session) is AsyncLazySession
    assert type(env._lazy_session.session) is ContreeAsyncSession
    assert type(env._lazy_session.operation).__name__ == "AsyncOperation"
    await env.stop(delete=True)


async def test_start_imports_oci_image_before_opening_session(backend):
    client, env = backend
    import contree_sdk.harbor.environment as module

    try:
        await env.start(force_build=False)
        assert isinstance(module.async_import_image, AsyncMock)
        module.async_import_image.assert_awaited_once_with(
            "alpine:latest",
            timeout=600,
            client=client,
            profile=None,
            client_type=None,
        )
        assert client.calls_for("spawn_instance")[0].args[1] == "base"
    finally:
        await env.stop()


@pytest.mark.parametrize("startup_fails", [False, True])
async def test_factory_owned_client_closes_on_stop_and_failed_start(backend, monkeypatch, startup_fails):
    _, env = backend
    from contree_client.profiles import Profile
    from tests.unit.session.test_sandbox_factory import FactoryAsyncClient

    import contree_sdk.harbor.environment as module

    profile = Profile(name="test", url="https://test.invalid", token="token", auth_type="iam")
    monkeypatch.setattr("contree_sdk.connection.ConnectionConfig.resolve_profile", lambda self: profile)
    monkeypatch.setattr(module, "HttpxAsyncClient", FactoryAsyncClient)
    env._client = None
    if startup_fails:

        async def fail_start(*args, **kwargs):
            raise ValueError("startup check failed")

        monkeypatch.setattr(env, "_execute", fail_start)
        with pytest.raises(ValueError, match="startup check failed"):
            await env.start(force_build=False)
    else:
        await env.start(force_build=False)
        await env.stop(delete=True)
    client = FactoryAsyncClient.instances[-1]
    assert client.opened == client.closed == 1
    assert env._lazy_session_context is None


async def test_start_retries_control_channel_readiness(backend, monkeypatch):
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
    assert attempts == 3  # two readiness responses, then log-dir creation
    await env.stop(delete=True)


async def test_download_file_streams_binary_chunks_without_snapshot(backend, tmp_path, monkeypatch):
    client, env = backend
    await env.start(force_build=False)
    payload = b"\x00" + b"x" * (256 * 1024 + 17)

    async def downloaded_chunks(operation_id, path):
        client.record_call("inspect_instance_download_stream", (operation_id, path), {})
        yield payload[: 256 * 1024]
        yield payload[256 * 1024 :]

    monkeypatch.setattr(client, "inspect_instance_download_stream", downloaded_chunks)
    target = tmp_path / "download.bin"
    await env.download_file("/remote/data.bin", target)
    assert target.read_bytes() == payload
    assert len(client.calls_for("spawn_instance")) == 1
    assert len(client.calls_for("operation_subprocess")) == 1  # log-dir creation only
    assert client.calls_for("inspect_instance_download_stream")[0].args == ("op-1", "/remote/data.bin")
    await env.stop(delete=True)


async def test_download_dir_uses_live_session_inspector(backend, tmp_path, monkeypatch):
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
        client.record_call("inspect_instance_archive", (operation_id, path), kwargs)
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
        assert client.calls_for("inspect_instance_archive")[0].args == ("op-1", "/remote/logs")
        assert len(client.calls_for("spawn_instance")) == 1
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


@pytest.mark.parametrize("cwd", [None, "/override"])
@pytest.mark.parametrize(("user", "uid"), [(None, ...), ("root", 0), (1000, 1000)])
async def test_exec_forwards_harbor_options_and_converts_the_result(backend, monkeypatch, cwd, user, uid):
    client, env = backend
    env.task_env_config.workdir = "/default"
    env._persistent_env = {"BASE": "persistent", "SHARED": "persistent"}
    await env.start(force_build=False)
    get_result = client.operation_subprocess
    client.exit_code = 7

    async def completed(operation_id, spid):
        result = await get_result(operation_id, spid)
        result.stdout = StreamRepr.from_bytes(b"output\xff")
        result.stderr = StreamRepr.from_text("error")
        return result

    monkeypatch.setattr(client, "operation_subprocess", completed)
    try:
        with env.scoped_exec_env({"SHARED": "scoped"}):
            result = await env.exec("echo example", cwd=cwd, env={"SHARED": "command"}, timeout_sec=1, user=user)
        call = client.calls_for("operation_subprocess_create")[-1]
        assert call.args == ("op-1", "/bin/bash")
        assert call.kwargs["args"] == ["-c", "echo example"]
        assert call.kwargs["cwd"] == (cwd or "/default")
        assert call.kwargs["env"] == {"BASE": "persistent", "SHARED": "scoped"}
        assert call.kwargs["truncate_output_at"] == 10 * 1024 * 1024
        assert call.kwargs["uid"] == uid
        assert result.return_code == 7
        assert result.stdout == "output�"
        assert result.stderr == "error"
    finally:
        await env.stop()


async def test_exec_cancellation_requests_child_kill(backend):
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
        assert client.calls_for("operation_subprocess_kill")[-1].kwargs["signal"] == "SIGKILL"
        client.auto_exit = True
        assert (await env.exec("next")).return_code == 0
        assert len(client.calls_for("spawn_instance")) == 1
    finally:
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)
        await env.stop()
