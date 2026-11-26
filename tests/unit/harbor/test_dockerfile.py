from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from contree_client.models import InstanceResult, InstanceResultState
from contree_client.types import ContreeAsyncClient


pytest.importorskip("harbor")

from harbor.models.task.config import EnvironmentConfig
from harbor.models.trial.paths import TrialPaths

from contree_sdk import AsyncLazySession
from contree_sdk.harbor import ConTreeEnvironment


@pytest.fixture
def client():
    return Mock(spec=ContreeAsyncClient)


@pytest.fixture
async def docker_environment(tmp_path, monkeypatch, client):
    session = AsyncMock(spec=AsyncLazySession)
    session.execute.return_value = InstanceResult(state=InstanceResultState(exit_code=0))
    context = MagicMock()
    context.__aenter__.return_value = session
    factory = Mock(return_value=context)
    build_image = AsyncMock(return_value="built-image")
    import_image = AsyncMock(return_value="imported-image")
    monkeypatch.setattr("contree_sdk.harbor.environment.create_async_sandbox_session", factory)
    monkeypatch.setattr("contree_sdk.harbor.environment.async_build_image", build_image)
    monkeypatch.setattr("contree_sdk.harbor.environment.async_import_image", import_image)
    environment_dir = tmp_path / "environment"
    environment_dir.mkdir()
    (environment_dir / "Dockerfile").write_text("FROM alpine:latest\nRUN true\n")
    environment = ConTreeEnvironment(
        environment_dir=environment_dir,
        environment_name="test",
        session_id="dockerfile",
        trial_paths=TrialPaths(trial_dir=tmp_path / "trial"),
        task_env_config=EnvironmentConfig(build_timeout_sec=123.5),
        contree_client=client,
    )
    yield environment, build_image, import_image, factory, session
    await environment.stop()


@pytest.mark.parametrize(
    ("docker_image", "has_dockerfile", "force_build", "build"),
    [
        (None, True, False, True),
        ("alpine:latest", True, False, False),
        ("alpine:latest", True, True, True),
        ("alpine:latest", False, True, False),
    ],
)
async def test_image_source_selection(docker_environment, client, docker_image, has_dockerfile, force_build, build):
    environment, build_image, import_image, factory, _ = docker_environment
    environment.task_env_config.docker_image = docker_image
    if not has_dockerfile:
        (environment.environment_dir / "Dockerfile").unlink()

    await environment.start(force_build=force_build)

    assert factory.call_args.kwargs["client"] is client
    if build:
        build_image.assert_awaited_once_with(environment.environment_dir, client=client, timeout=124)
        import_image.assert_not_awaited()
    else:
        import_image.assert_awaited_once_with(docker_image, client=client, timeout=environment.IMAGE_IMPORT_TIMEOUT_SEC)
        build_image.assert_not_awaited()
    assert factory.call_args.kwargs["image"] == ("built-image" if build else "imported-image")


async def test_failed_build_does_not_start_session(docker_environment):
    environment, build_image, _, factory, _ = docker_environment
    error = ValueError("build failed")
    build_image.side_effect = error

    with pytest.raises(ValueError) as raised:
        await environment.start(force_build=False)

    assert raised.value is error
    factory.assert_not_called()


def test_missing_image_and_dockerfile(tmp_path):
    with pytest.raises(ValueError, match="docker_image or environment/Dockerfile"):
        ConTreeEnvironment(
            environment_dir=tmp_path,
            environment_name="test",
            session_id="missing",
            trial_paths=TrialPaths(trial_dir=tmp_path / "trial"),
            task_env_config=EnvironmentConfig(),
        )
