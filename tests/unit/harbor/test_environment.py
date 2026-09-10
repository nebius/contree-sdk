import asyncio
import io
import os
import pwd
import subprocess
import sys
import tarfile
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


if sys.version_info < (3, 12):
    pytest.skip("Harbor requires Python 3.12+", allow_module_level=True)
pytest.importorskip("harbor")
pytest.importorskip("httpx")

from harbor.environments.base import ExecResult
from harbor.environments.factory import EnvironmentFactory
from harbor.models.task.config import EnvironmentConfig, NetworkMode, NetworkPolicy
from harbor.models.trial.paths import TrialPaths

from contree_sdk.harbor import ConTreeEnvironment
from tests.unit.fixtures.files import queue_upload
from tests.unit.fixtures.operations import queue_run


@pytest.fixture
def env_kwargs(tmp_path, fake_contree):
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir()
    return {
        "environment_dir": environment_dir,
        "environment_name": "test",
        "session_id": "test__env",
        "trial_paths": TrialPaths(trial_dir=tmp_path / "trial"),
        "task_env_config": EnvironmentConfig(docker_image="ubuntu:24.04"),
        "client": fake_contree,
    }


@pytest.fixture
async def environment(env_kwargs, fake_contree, fake_image, fake_api, monkeypatch):
    monkeypatch.setattr(fake_contree.images, "pull_image_by_oci", AsyncMock(return_value=fake_image))
    queue_run(fake_api, result_image_uuid=str(uuid4()))
    queue_run(fake_api, result_image_uuid=str(uuid4()))
    env = ConTreeEnvironment(**env_kwargs)
    await env.start(force_build=False)
    for operation in ("spawn_instance", "follow_operation_events", "get_operation_status"):
        fake_api.mocks[operation].clear()
    yield env
    await env.stop(delete=True)


def test_factory_import(env_kwargs):
    environment = EnvironmentFactory.create_environment_from_import_path(
        "contree_sdk.harbor:ConTreeEnvironment", **env_kwargs
    )
    assert isinstance(environment, ConTreeEnvironment)
    assert environment.type() == "contree"
    assert not any(environment.capabilities.model_dump().values())
    resources = environment.resource_capabilities()
    assert resources is not None
    assert not any(resources.model_dump().values())


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"docker_image": None}, "requires.*docker_image"),
        ({"gpus": 1}, "GPU"),
        ({"gpu_types": ["H100"]}, "GPU"),
        ({"os": "windows"}, "Windows"),
        ({"network_mode": "no-network"}, "network"),
        ({"network_mode": "allowlist", "allowed_hosts": ["example.com"]}, "allowlist"),
        ({"mcp_servers": [{"name": "test", "url": "https://example.com"}]}, "MCP"),
        ({"build_timeout_sec": 0}, "build_timeout_sec"),
    ],
)
def test_unsupported_task_config(env_kwargs, config, message):
    env_kwargs["task_env_config"] = EnvironmentConfig.model_validate({"docker_image": "ubuntu:24.04", **config})
    with pytest.raises((ValueError, RuntimeError), match=message):
        ConTreeEnvironment(**env_kwargs)


@pytest.mark.parametrize("option", ["cpu_enforcement_policy", "memory_enforcement_policy"])
@pytest.mark.parametrize("mode", ["limit", "request", "guarantee"])
def test_resource_enforcement_rejected(env_kwargs, option, mode):
    with pytest.raises(ValueError, match="resource"):
        ConTreeEnvironment(**env_kwargs, **{option: mode})


@pytest.mark.parametrize(
    ("storage_mb", "override_storage_mb", "effective_storage_mb"),
    [(1024, None, 1024), (None, 10, 10), (1024, 10, 10), (None, None, None)],
)
def test_storage_requests_warn(env_kwargs, caplog, storage_mb, override_storage_mb, effective_storage_mb):
    env_kwargs["task_env_config"].storage_mb = storage_mb
    ConTreeEnvironment(**env_kwargs, override_storage_mb=override_storage_mb)
    warnings = [record for record in caplog.records if "storage resources" in record.message]
    if effective_storage_mb is None:
        assert not warnings
    else:
        assert len(warnings) == 1
        assert warnings[0].levelname == "WARNING"
        assert f"storage_mb={effective_storage_mb}" in warnings[0].message
        assert "ignored" in warnings[0].message


def test_future_phase_network_rejected(env_kwargs):
    with pytest.raises(ValueError, match="network"):
        ConTreeEnvironment(**env_kwargs, phase_network_policies=[NetworkPolicy(network_mode=NetworkMode.NO_NETWORK)])


def test_custom_mount_rejected(env_kwargs):
    with pytest.raises(ValueError, match="mounts"):
        ConTreeEnvironment(**env_kwargs, mounts=[{"type": "bind", "source": "/host/data", "target": "/data"}])


def test_harbor_log_mounts_accepted(env_kwargs):
    paths = env_kwargs["trial_paths"]
    env = ConTreeEnvironment(
        **env_kwargs,
        mounts=[{"type": "bind", "source": str(paths.agent_dir), "target": "/logs/agent"}],
    )
    assert not env.capabilities.mounted


def test_unknown_options_rejected(env_kwargs):
    with pytest.raises(TypeError, match=r"Unknown.*typo"):
        ConTreeEnvironment(**env_kwargs, typo=True)


async def test_dockerfile_prebuilt_and_force_build(env_kwargs, fake_contree, fake_image, fake_api, monkeypatch):
    (env_kwargs["environment_dir"] / "Dockerfile").write_text("FROM ubuntu:24.04")
    env = ConTreeEnvironment(**env_kwargs)
    with pytest.raises(ValueError, match="force-build"):
        await env.start(force_build=True)
    monkeypatch.setattr(fake_contree.images, "pull_image_by_oci", AsyncMock(return_value=fake_image))
    queue_run(fake_api, result_image_uuid=str(uuid4()))
    queue_run(fake_api, result_image_uuid=str(uuid4()))
    await env.start(force_build=False)
    assert len(fake_api.calls_for("spawn_instance")) == 2
    await env.stop(delete=True)


def test_compose_rejected(env_kwargs):
    (env_kwargs["environment_dir"] / "docker-compose.yaml").write_text("services: {}")
    with pytest.raises(ValueError, match="Compose"):
        ConTreeEnvironment(**env_kwargs)


async def test_exec_advances_state_even_on_nonzero_exit(environment, fake_api):
    next_image = str(uuid4())
    queue_run(fake_api, stdout="out", stderr="error", exit_code=7, result_image_uuid=next_image)
    result = await environment.exec("echo out; echo error >&2; exit 7")
    assert result == ExecResult(stdout="out", stderr="error", return_code=7)
    for operation in ("spawn_instance", "follow_operation_events", "get_operation_status"):
        fake_api.mocks[operation].clear()
    queue_run(fake_api, stdout="next", result_image_uuid=str(uuid4()))
    await environment.exec("cat saved-file")
    calls = fake_api.calls_for("spawn_instance")
    assert calls[-1].args[1] == next_image
    assert all(call.kwargs["disposable"] is False for call in calls)


async def test_env_precedence_workdir_and_user(environment, fake_api):
    environment.task_env_config.workdir = "/app"
    environment._persistent_env = {"X": "persistent", "Y": "persistent"}
    queue_run(fake_api, result_image_uuid=str(uuid4()))
    with environment.scoped_exec_env({"X": "scoped"}):
        await environment.exec("pwd", env={"X": "call", "Y": "call"}, timeout_sec=17, user=0)
    call = fake_api.calls_for("spawn_instance")[-1]
    assert call.args[0] == "/bin/bash"
    assert call.kwargs["shell"] is False
    assert call.kwargs["args"][0] == "-c"
    assert call.kwargs["env"] == {"X": "scoped", "Y": "call"}
    assert call.kwargs["cwd"] == "/app"
    assert call.kwargs["timeout"] == 17
    assert call.kwargs["preserve_env"] is True
    with environment.with_default_user("nobody"), pytest.raises(ValueError, match="switching users"):
        await environment.exec("id")


@pytest.mark.parametrize(
    ("image_env", "command_env", "expected"),
    [
        ({}, {}, None),
        ({}, {"SHELL": "/nonexistent-shell"}, None),
        ({"HOME": "/image home"}, {}, "/image home"),
        ({"HOME": "/image home"}, {"HOME": "/command home"}, "/command home"),
        ({}, {"HOME": ""}, ""),
    ],
)
async def test_home_fallback(environment, fake_api, image_env, command_env, expected):
    queue_run(fake_api, result_image_uuid=str(uuid4()))
    await environment.exec("printenv HOME", env=command_env)
    call = fake_api.calls_for("spawn_instance")[-1]
    # Execute the actual executable and arguments sent to ConTree.
    # The fallback must also export HOME to the command's child processes.
    result = await asyncio.to_thread(
        subprocess.run,
        [call.args[0], *call.kwargs["args"]],
        env={**image_env, **call.kwargs["env"]},
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == (pwd.getpwuid(os.getuid()).pw_dir if expected is None else expected) + "\n"


async def test_output_callback(environment, fake_api):
    queue_run(fake_api, stdout="héllo", stderr="error", result_image_uuid=str(uuid4()))
    callback = AsyncMock()
    with environment.scoped_output_callback(callback):
        result = await environment.exec("echo hello")
    assert result.stdout == "héllo"
    callback.assert_any_await("héllo", "stdout")
    callback.assert_any_await("error", "stderr")


async def test_concurrent_execs_share_updated_snapshot(environment, fake_api):
    first, second = str(uuid4()), str(uuid4())
    queue_run(fake_api, stdout="first", result_image_uuid=first)
    queue_run(fake_api, stdout="second", result_image_uuid=second)
    results = await asyncio.gather(environment.exec("first"), environment.exec("second"))
    assert [result.stdout for result in results] == ["first", "second"]
    assert fake_api.calls_for("spawn_instance")[-1].args[1] == first


async def test_timeout_keeps_last_completed_snapshot(environment, fake_api):
    previous = environment._session.uuid
    queue_run(fake_api, timed_out=True, result_image_uuid=None)
    with pytest.raises(TimeoutError):
        await environment.exec("sleep 60", timeout_sec=1)
    for operation in ("spawn_instance", "follow_operation_events", "get_operation_status"):
        fake_api.mocks[operation].clear()
    queue_run(fake_api, stdout="old logs", result_image_uuid=str(uuid4()))
    await environment.exec("cat /logs/agent/log")
    assert fake_api.calls_for("spawn_instance")[-1].args[1] == str(previous)


async def test_stop_is_idempotent_and_keeps_injected_client_open(environment, fake_api):
    previous = environment._session.uuid
    await environment.stop(delete=True)
    await environment.stop(delete=True)
    assert environment.final_image_uuid == previous
    assert not fake_api.calls_for("delete_image_tag")
    with pytest.raises(RuntimeError, match="not running"):
        await environment.exec("true")


async def test_retention_tags_only_final_image(environment, fake_api):
    fake_api.mock("update_image_tag", None)
    previous = environment._session.uuid
    await environment.stop(delete=False)
    call = fake_api.calls_for("update_image_tag")[-1]
    assert call.args == (str(previous), environment.retained_image_tag)
    assert environment.retained_image_tag.startswith("harbor-")
    assert not fake_api.calls_for("delete_image_tag")


async def test_upload_file_preserves_mode(environment, fake_api, tmp_path, file_uuid, file_sha256):
    source = tmp_path / "solve.sh"
    source.write_text("echo hi")
    source.chmod(0o755)
    queue_upload(fake_api, file_uuid, file_sha256)
    queue_run(fake_api, result_image_uuid=str(uuid4()))
    await environment.upload_file(source, "/solution/solve.sh")
    spec = fake_api.calls_for("spawn_instance")[-1].kwargs["files"]["/solution/solve.sh"]
    assert spec.mode == f"{source.stat().st_mode & 0o777:04o}"


async def test_download_file_creates_parent(environment, fake_api, tmp_path):
    fake_api.mock("inspect_image_download", b"reward")
    target = tmp_path / "nested" / "reward.txt"
    await environment.download_file("/logs/verifier/reward.txt", target)
    assert target.read_bytes() == b"reward"


async def test_download_dir_preserves_files_and_rejects_escape(environment, fake_api, tmp_path):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        entry = tarfile.TarInfo("solve.sh")
        entry.mode = 0o755
        entry.size = 7
        archive.addfile(entry, io.BytesIO(b"echo hi"))
        empty = tarfile.TarInfo("empty")
        empty.type = tarfile.DIRTYPE
        archive.addfile(empty)
        escape = tarfile.TarInfo("../outside")
        archive.addfile(escape)
    fake_api.mock("inspect_image_archive", [buffer.getvalue()])
    target = tmp_path / "download"
    await environment.download_dir("/solution", target)
    assert (target / "solve.sh").read_text() == "echo hi"
    assert (target / "empty").is_dir()
    assert not (tmp_path / "outside").exists()
    if sys.platform != "win32":
        assert (target / "solve.sh").stat().st_mode & 0o111


async def test_upload_dir_includes_empty_dirs_and_symlinks(environment, fake_api, tmp_path, file_uuid, file_sha256):
    source = tmp_path / "source"
    source.mkdir()
    (source / "empty").mkdir()
    (source / "solve.sh").write_text("echo hi")
    (source / "solve.sh").chmod(0o755)
    if sys.platform != "win32":
        (source / "link").symlink_to("solve.sh")
    queue_upload(fake_api, file_uuid, file_sha256)
    queue_run(fake_api, result_image_uuid=str(uuid4()))
    await environment.upload_dir(source, "/solution with spaces")
    call = fake_api.calls_for("spawn_instance")[-1]
    assert "'/solution with spaces'" in call.kwargs["args"][1]
    assert len(call.kwargs["files"]) == 1
    uploaded = fake_api.calls_for("ensure_file")[-1].args[0]
    # The testing transport records the uploaded bytes before the temporary
    # archive is removed by the adapter.
    with tarfile.open(fileobj=io.BytesIO(uploaded), mode="r:gz") as archive:
        assert archive.getmember("./empty").isdir()
        assert archive.getmember("./solve.sh").mode & 0o111 or sys.platform == "win32"
        if sys.platform != "win32":
            assert archive.getmember("./link").issym()


async def test_startup_uploads_environment_to_image_workdir(
    env_kwargs, fake_contree, fake_image, fake_api, monkeypatch, file_uuid, file_sha256
):
    (env_kwargs["environment_dir"] / "input.txt").write_text("task input")
    monkeypatch.setattr(fake_contree.images, "pull_image_by_oci", AsyncMock(return_value=fake_image))
    for output in ("/bin/bash\n/bin/tar\n", "", "/workspace\n", ""):
        queue_run(fake_api, stdout=output, result_image_uuid=str(uuid4()))
    queue_upload(fake_api, file_uuid, file_sha256)
    env = ConTreeEnvironment(**env_kwargs)
    await env.start(force_build=False)
    calls = fake_api.calls_for("spawn_instance")
    assert calls[-2].kwargs["args"][1].endswith("\npwd")
    assert "-C /workspace" in calls[-1].kwargs["args"][1]
    assert len(calls[-1].kwargs["files"]) == 1
    await env.stop(delete=True)


async def test_owned_client_closed_on_start_failure(env_kwargs, fake_contree, fake_api, fake_image, monkeypatch):
    env_kwargs.pop("client")
    monkeypatch.setattr("contree_sdk.harbor.environment.ContreeAsyncClient.from_profile", lambda profile: fake_api)
    monkeypatch.setattr("contree_sdk.harbor.environment.Contree", lambda *args, **kwargs: fake_contree)
    monkeypatch.setattr(fake_contree.images, "pull_image_by_oci", AsyncMock(return_value=fake_image))
    close = AsyncMock()
    monkeypatch.setattr(fake_api, "close", close)
    queue_run(fake_api, exit_code=1, result_image_uuid=str(uuid4()))
    env = ConTreeEnvironment(**env_kwargs)
    with pytest.raises(RuntimeError, match="root with Bash and tar"):
        await env.start(force_build=False)
    close.assert_awaited_once()
    await env.stop(delete=True)
    close.assert_awaited_once()


@pytest.mark.parametrize("cancel_via_stop", [False, True])
async def test_cancellation_cancels_remote_operation(environment, fake_api, monkeypatch, cancel_via_stop):
    entered = asyncio.Event()
    pending = asyncio.Event()
    queue_run(fake_api, result_image_uuid=str(uuid4()))
    previous = environment._session.uuid
    cancel = AsyncMock()
    monkeypatch.setattr(fake_api, "cancel_operation", cancel)

    async def events(*args, **kwargs):
        entered.set()
        await pending.wait()
        yield None  # Cancellation happens before this event can be yielded.

    monkeypatch.setattr(fake_api, "follow_operation_events", events)
    task = asyncio.create_task(environment.exec("sleep 60"))
    await asyncio.wait_for(entered.wait(), timeout=5)
    if cancel_via_stop:
        await environment.stop(delete=True)
    else:
        task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    cancel.assert_awaited_once()
    if cancel_via_stop:
        assert environment.final_image_uuid == previous
    else:
        assert environment._session.uuid == previous


async def test_owned_client_closed_after_success(env_kwargs, fake_contree, fake_api, fake_image, monkeypatch):
    env_kwargs.pop("client")
    factory = AsyncMock()
    # Profile creation is synchronous; the transport itself is async.
    monkeypatch.setattr("contree_sdk.harbor.environment.ContreeAsyncClient.from_profile", lambda profile: fake_api)
    monkeypatch.setattr("contree_sdk.harbor.environment.Contree", lambda *args, **kwargs: fake_contree)
    monkeypatch.setattr(fake_contree.images, "pull_image_by_oci", AsyncMock(return_value=fake_image))
    monkeypatch.setattr(fake_api, "close", factory)
    queue_run(fake_api, result_image_uuid=str(uuid4()))
    env = ConTreeEnvironment(**env_kwargs)
    await env.start(force_build=False)
    await env.stop(delete=True)
    await env.stop(delete=True)
    factory.assert_awaited_once()


def test_example_is_discoverable():
    from harbor.models.task.task import Task

    path = Path(__file__).resolve().parents[3] / "examples" / "harbor"
    assert Task.is_valid_dir(path)
    assert Task(path).config.environment.docker_image == "docker.io/library/ubuntu:24.04"
