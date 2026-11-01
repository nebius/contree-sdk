import asyncio
import io
import tarfile
from unittest.mock import AsyncMock

import pytest
from contree_client.models import EventDataStream, FileResponse, OperationEventType, StreamRepr


pytest.importorskip("harbor")

from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.config import EnvironmentConfig
from harbor.models.trial.paths import TrialPaths
from tests.unit.session.lazy_clients import LiveAsyncClient, event

from contree_sdk.harbor import ConTreeEnvironment


@pytest.fixture
def backend(tmp_path, monkeypatch):
    client = LiveAsyncClient()
    client.auto_main_spawn = True
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


async def test_vm_persists_across_exec_and_file_transfers(backend, tmp_path):
    client, env = backend
    await env.start(force_build=False)
    assert len(client.calls_for("spawn_instance")) == 1
    assert client.calls_for("spawn_instance")[0].kwargs["timeout"] == 3600
    result = await env.exec("printf hello")
    assert result.return_code == 0
    assert len(client.calls_for("spawn_instance")) == 1
    source = tmp_path / "source.txt"
    source.write_text("hello")
    await env.upload_file(source, "/app/source.txt")
    await env.upload_dir(env.environment_dir, "/work")
    assert len(client.calls_for("spawn_instance")) == 1
    assert len(client.calls_for("apply_instance_file")) == 2
    assert all(call.kwargs["merge"] for call in client.calls_for("apply_instance_file"))
    assert not client.calls_for("operation_subprocess_stdin")
    await env.stop(delete=True)
    assert not client.calls_for("cancel_operation")
    assert client.calls_for("get_operation_status")


async def test_commands_use_one_operation(backend):
    client, env = backend
    await env.start(force_build=False)
    await env.exec("true")
    await env.exec("true")
    assert len(client.calls_for("spawn_instance")) == 1
    assert len(client.calls_for("operation_subprocess_create")) == 3
    await env.stop(delete=True)


@pytest.mark.parametrize(
    "stop_kwargs", [{}, {"delete": True}, {"delete": False}], ids=["default", "delete", "no-delete"]
)
async def test_stop_saves_final_operation_without_tagging(backend, stop_kwargs):
    client, env = backend
    await env.start(force_build=False)
    await env.exec("true")
    operation = env._operation
    await env.stop(**stop_kwargs)
    assert operation.terminal
    assert not client.calls_for("cancel_operation")
    assert not client.calls_for("update_image_tag")
    assert env._operation is None
    assert env._client is client
    assert len(client.calls_for("get_operation_status")) == 1
    await env.stop(**stop_kwargs)
    assert len(client.calls_for("get_operation_status")) == 1


async def test_failed_close_aborts_operation_and_releases_context(backend):
    client, env = backend
    await env.start(force_build=False)
    operation = env._operation
    client.wait_error = OSError("snapshot failed")
    with pytest.raises(OSError, match="snapshot failed"):
        await env.stop()
    assert operation.terminal
    assert client.calls_for("cancel_operation")
    assert not client.calls_for("update_image_tag")
    assert env._operation is None
    assert env._client is client


async def test_stop_rejects_missing_final_image(backend):
    client, env = backend
    await env.start(force_build=False)
    client.result_image = False
    with pytest.raises(RuntimeError, match="did not save"):
        await env.stop()
    assert client.calls_for("cancel_operation")
    assert env._operation is None


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
            vm_timeout=0,
        )


async def test_environment_uses_sdk_operation_and_transfer(backend):
    client, env = backend
    from contree_sdk.files import AsyncClientFileTransfer
    from contree_sdk.session.operation_async import AsyncOperation

    await env.start(force_build=False)
    assert type(env._operation) is AsyncOperation
    assert type(env._transfer) is AsyncClientFileTransfer
    assert env._operation.client is client
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
    monkeypatch.setattr(module.profiles, "resolve_profile", lambda *args: profile)
    monkeypatch.setattr(module.profiles, "from_env", lambda: None)
    monkeypatch.setattr(module, "HttpxAsyncClient", FactoryAsyncClient)
    monkeypatch.setattr(FactoryAsyncClient, "auto_main_spawn", True)
    env._client = env._provided_client = None
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
    assert env._client is None


async def test_start_waits_for_main_process_before_creating_subprocess(backend):
    client, env = backend
    client.auto_main_spawn = False
    start = asyncio.create_task(env.start(force_build=False))
    async with asyncio.timeout(1):
        while "op-1" not in client.streams:
            await asyncio.sleep(0)
    assert not client.calls_for("operation_subprocess_create")
    await client.streams["op-1"].put(event("spawn"))
    await start
    assert len(client.calls_for("operation_subprocess_create")) == 1
    await env.stop(delete=True)


async def test_start_readiness_timeout_cancels_unstarted_operation(backend):
    client, env = backend
    client.auto_main_spawn = False
    env._readiness_timeout = 0.01

    with pytest.raises(TimeoutError, match="did not become ready"):
        await env.start(force_build=False)

    assert client.calls_for("cancel_operation")
    assert not client.calls_for("operation_subprocess_create")
    assert env._operation is None


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

    async def archived(operation_id, path, **kwargs):
        client.record_call("inspect_instance_archive", (operation_id, path), kwargs)
        yield archive.getvalue()

    monkeypatch.setattr(client, "inspect_instance_archive", archived)
    destination = tmp_path / "logs"
    destination.mkdir()
    (destination / "existing.txt").write_text("keep")
    try:
        await env.download_dir("/remote/logs", destination)
        assert (destination / "nested/log.txt").read_bytes() == b"log contents\n"
        assert (destination / "existing.txt").read_text() == "keep"
        assert client.calls_for("inspect_instance_archive")[0].args == ("op-1", "/remote/logs")
        assert len(client.calls_for("spawn_instance")) == 1
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


async def test_exec_streams_only_its_process_with_best_effort_text(backend, monkeypatch):
    client, env = backend
    await env.start(force_build=False)
    create = client.operation_subprocess_create
    client.auto_exit = False
    received = []

    async def create_output(operation_id, command, **kwargs):
        spid = await create(operation_id, command, **kwargs)
        chunks: list[tuple[OperationEventType, bytes]] = [
            ("stdout", b"\xe2\x82"),
            ("stderr", b"err "),
            ("stdout", b"\xac"),
            ("stderr", b"\xe2"),
        ]
        for kind, data in chunks:
            chunk = event(kind, spid)
            chunk.data = EventDataStream.from_bytes(data)
            client.streams[operation_id].put_nowait(chunk)
        client.streams[operation_id].put_nowait(event("exit", spid))
        return spid

    def reject_history_scan(**kwargs):
        raise AssertionError("Command output must use the subprocess queue")

    async def callback(text, stream):
        received.append((text, stream))

    monkeypatch.setattr(client, "operation_subprocess_create", create_output)
    monkeypatch.setattr(env._operation, "events", reject_history_scan)
    try:
        with env.scoped_output_callback(callback):
            await env.exec("first")
            await env.exec("second")
        assert received == [("�", "stdout"), ("err ", "stderr"), ("�", "stdout"), ("�", "stderr")] * 2
        assert len(client.calls_for("spawn_instance")) == 1
    finally:
        await env.stop()


@pytest.mark.parametrize("confirmed", [True, False])
async def test_exec_cancellation_confirms_kill_or_aborts_the_operation(backend, monkeypatch, confirmed):
    client, env = backend
    await env.start(force_build=False)
    client.auto_exit = False
    client.created.clear()
    env._terminate_timeout = 0.02
    if not confirmed:

        async def unconfirmed_kill(operation_id, spid, **kwargs):
            client.record_call("operation_subprocess_kill", (operation_id, spid), kwargs)

        monkeypatch.setattr(client, "operation_subprocess_kill", unconfirmed_kill)
    running = asyncio.create_task(env.exec("sleep 100"))
    try:
        await asyncio.wait_for(client.created.wait(), 1)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(running, 1)
        assert client.calls_for("operation_subprocess_kill")[-1].kwargs["signal"] == "SIGKILL"
        if confirmed:
            assert not client.calls_for("cancel_operation")
            client.auto_exit = True
            assert (await env.exec("next")).return_code == 0
            assert len(client.calls_for("spawn_instance")) == 1
        else:
            assert client.calls_for("cancel_operation")
            assert env._operation.cancel_requested
    finally:
        running.cancel()
        await asyncio.gather(running, return_exceptions=True)
        await env.stop()


async def test_output_callback_failure_kills_child_and_reuses_vm(backend, monkeypatch):
    client, env = backend
    await env.start(force_build=False)
    client.auto_exit = False

    async def create_output(operation_id, command, **kwargs):
        spid = await original_create(operation_id, command, **kwargs)
        output = event("stdout", spid)
        output.data = EventDataStream.from_bytes(b"hello")
        client.streams[operation_id].put_nowait(output)
        return spid

    async def fail_callback(text, stream):
        raise ValueError("callback failed")

    original_create = client.operation_subprocess_create
    monkeypatch.setattr(client, "operation_subprocess_create", create_output)
    try:
        with env.scoped_output_callback(fail_callback), pytest.raises(ValueError, match="callback failed"):
            await env.exec("echo hello")
        assert client.calls_for("operation_subprocess_kill")
        client.auto_exit = True
        assert (await env.exec("true")).return_code == 0
        assert len(client.calls_for("spawn_instance")) == 1
    finally:
        await env.stop()
