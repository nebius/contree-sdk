import pytest
from contree_client.exceptions import ConflictError, TooEarlyError
from contree_client.models import InstanceResult, InstanceResultState, StreamRepr
from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.config import EnvironmentConfig
from harbor.models.trial.paths import TrialPaths

from contree_sdk.harbor import ConTreeEnvironment
from tests.unit.session.lazy_clients import LiveAsyncClient, event


@pytest.fixture
def backend(tmp_path):
    client = LiveAsyncClient()
    client.mock("operation_subprocess_stdin", None)
    client.mock("update_image_tag", None)
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir()
    env = ConTreeEnvironment(
        environment_dir=environment_dir,
        environment_name="test",
        session_id="test__env",
        trial_paths=TrialPaths(trial_dir=tmp_path / "trial"),
        task_env_config=EnvironmentConfig(docker_image="uuid:base"),
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
    client.auto_exit = False
    create = client.operation_subprocess_create

    async def spawn_with_event(operation_id, command, **kwargs):
        spid = await create(operation_id, command, **kwargs)
        await client.streams[operation_id].put(event("spawn", spid))
        return spid

    client.operation_subprocess_create = spawn_with_event

    async def acknowledge_stdin(operation_id, spid, value, **kwargs):
        client.record_call("operation_subprocess_stdin", (operation_id, spid, value), kwargs)
        if kwargs.get("close"):
            await client.streams[operation_id].put(event("exit", spid))

    client.operation_subprocess_stdin = acknowledge_stdin
    await env.upload_file(source, "/app/source.txt")
    await env.upload_dir(env.environment_dir, "/work")
    assert len(client.calls_for("spawn_instance")) == 1
    assert client.calls_for("operation_subprocess_stdin")
    commands = client.calls_for("operation_subprocess_create")
    assert any(getattr(call.kwargs.get("stdin"), "close", True) is False for call in commands)
    assert all(call.kwargs.get("close") for call in client.calls_for("operation_subprocess_stdin") if not call.args[2])
    await env.stop(delete=True)
    assert len(client.calls_for("cancel_operation")) == 1
    assert not client.calls_for("get_operation_status")


async def test_explicit_snapshot_restarts_from_saved_image(backend):
    client, env = backend
    await env.start(force_build=False)
    first_operation = client.calls_for("spawn_instance")[0].args[1]
    await env.exec("true")
    image = await env.snapshot()
    assert image == "image-op-1"
    await env.exec("true")
    starts = client.calls_for("spawn_instance")
    assert [start.args[1] for start in starts] == [first_operation, image]
    await env.stop(delete=True)


async def test_keep_image_tags_confirmed_snapshot(backend):
    client, env = backend
    await env.start(force_build=False)
    await env.exec("true")
    await env.stop(delete=False)
    assert env.final_image_uuid == "image-op-1"
    assert env.retained_image_tag.startswith("harbor-")
    assert client.calls_for("update_image_tag")


async def test_timeout_kills_child_and_reuses_vm(backend):
    client, env = backend
    await env.start(force_build=False)
    client.auto_exit = False
    with pytest.raises(TimeoutError):
        await env.exec("sleep 100", timeout_sec=0.02)
    assert client.calls_for("operation_subprocess_kill")[-1].args == ("op-1", 4)
    client.auto_exit = True
    await env.exec("true")
    assert len(client.calls_for("spawn_instance")) == 1
    await env.stop(delete=True)


async def test_invalid_config_and_paths(backend, tmp_path):
    _, env = backend
    with pytest.raises(ValueError, match="absolute"):
        await env.upload_file(tmp_path / "missing", "relative")
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
    assert type(env._lazy) is AsyncLazySession
    assert type(env._session) is ContreeAsyncSession
    assert type(env._lazy.operation).__name__ == "AsyncOperation"
    await env.stop(delete=True)


@pytest.mark.parametrize("startup_fails", [False, True])
async def test_factory_owned_client_closes_on_stop_and_failed_start(backend, monkeypatch, startup_fails):
    _, env = backend
    from contree_client.profiles import Profile

    import contree_sdk.harbor.environment as module
    from tests.unit.session.test_sandbox_factory import FactoryAsyncClient

    profile = Profile(name="test", url="https://test.invalid", token="token", auth_type="iam")
    monkeypatch.setattr("contree_sdk.connection.ConnectionConfig.resolve_profile", lambda self: profile)
    monkeypatch.setattr(module, "HttpxAsyncClient", FactoryAsyncClient)
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
    assert env._sandbox is None


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
    assert attempts == 4  # two readiness responses, startup check, log-dir creation
    await env.stop(delete=True)


async def test_download_file_streams_binary_chunks_without_snapshot(backend, tmp_path, monkeypatch):
    client, env = backend
    await env.start(force_build=False)
    payload = b"\x00" + b"x" * (256 * 1024 + 17)

    async def downloaded_chunk(operation_id, spid):
        client.record_call("operation_subprocess", (operation_id, spid), {})
        request = client.calls_for("operation_subprocess_create")[-1]
        command = request.kwargs["args"][1]
        offset = int(command.split(" skip=")[1].split()[0]) * 256 * 1024
        return InstanceResult(
            state=InstanceResultState(exit_code=0), stdout=StreamRepr.from_bytes(payload[offset : offset + 256 * 1024])
        )

    monkeypatch.setattr(client, "operation_subprocess", downloaded_chunk)
    target = tmp_path / "download.bin"
    await env.download_file("/remote/data.bin", target)
    assert target.read_bytes() == payload
    assert len(client.calls_for("spawn_instance")) == 1
    assert len(client.calls_for("operation_subprocess")) == 4  # startup checks plus two data chunks
    await env.stop(delete=True)
