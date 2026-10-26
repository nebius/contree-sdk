import asyncio
import inspect
from dataclasses import replace
from pathlib import Path

import pytest
from contree_client.exceptions import APIConnectionError, NotFoundError
from contree_client.models import FileResponse, ImageImportRegistry, ImageImportRegistryCredentials, OperationStatus
from contree_client.profiles import Profile
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk import async_build_image, async_import_image, sync_build_image, sync_import_image
from contree_sdk.docker import ContreeAsyncDockerBuilder, ContreeDockerBuilder
from contree_sdk.exceptions import FailedOperationError
from contree_sdk.images import image_cache_directory
from contree_sdk.store import AsyncMemoryStore, SyncMemoryStore
from tests.unit.session.factories import mock_completion, operation_response, spawn_response


class TrackingClient(ContreeClient):
    instances = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.opened = 0
        self.closed = 0
        self.instances.append(self)
        seed(self)

    def open(self):
        self.opened += 1

    def close(self):
        self.closed += 1


class TrackingAsyncClient(ContreeAsyncClient):
    instances = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.opened = 0
        self.closed = 0
        self.instances.append(self)
        seed(self)

    async def open(self):
        self.opened += 1

    async def close(self):
        self.closed += 1


def seed(client):
    client.mock("resolve_image", "base")
    client.mock("check_image_archive", True)
    client.mock("check_file_exists", True)
    client.mock("import_image", "import-1")
    client.mock("wait_operation", operation_response(operation_uuid="import-1", result_image_uuid="imported"))
    client.mock("update_image_tag", None)
    client.mock("cancel_operation", None)
    client.mock("ensure_file", FileResponse(uuid="file-1", sha256="a" * 64, size=4))
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response(result_image_uuid="built"))


async def invoke(function, *args, **kwargs):
    result = function(*args, **kwargs)
    return await result if inspect.isawaitable(result) else result


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    TrackingClient.instances.clear()
    TrackingAsyncClient.instances.clear()


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def mode(request):
    return request.param


@pytest.fixture
def api(mode):
    return TrackingAsyncClient if mode else TrackingClient


@pytest.fixture
def profile():
    return Profile(name="test", token="secret", url="https://test.invalid", project="project", auth_type="iam")


@pytest.fixture
def context(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM base\nCOPY message.txt /message.txt\nRUN cat /message.txt\n")
    (tmp_path / "message.txt").write_text("hello\n")
    return tmp_path


async def test_import_default_cache_persists_across_calls(mode, api, profile, tmp_path):
    helper = async_import_image if mode else sync_import_image
    for _ in range(2):
        assert await invoke(helper, "alpine:latest", profile=profile, client_type=api, tag="base") == "imported"
    first, second = api.instances
    assert first.calls_for("import_image")[0].args[0].url == "docker://docker.io/library/alpine:latest"
    assert first.calls_for("wait_operation")[0].kwargs == {"timeout": 300}
    assert not first.calls_for("follow_operation_events")
    assert not second.calls_for("import_image")
    assert second.calls_for("update_image_tag")[0].args == ("imported", "base")
    assert first.opened == first.closed == second.opened == second.closed == 1
    assert (tmp_path / "xdg/contree/images.sqlite3").is_file()
    assert b"secret" not in (tmp_path / "xdg/contree/images.sqlite3").read_bytes()


async def test_import_refresh_and_zero_ttl(mode, api, profile):
    helper = async_import_image if mode else sync_import_image
    for options in [{}, {"no_cache": True, "cache_ttl": 0}, {}]:
        await invoke(helper, "alpine:latest", profile=profile, client_type=api, **options)
    assert all(len(c.calls_for("import_image")) == 1 for c in api.instances)


async def test_import_wait_failure_cancels_without_sdk_status_fallback(mode, api):
    client = api()
    cache = AsyncMemoryStore() if mode else SyncMemoryStore()
    error = APIConnectionError("status polling failed")
    client.mocks["wait_operation"].clear()
    client.mock("wait_operation", error=error)
    helper = async_import_image if mode else sync_import_image
    with pytest.raises(APIConnectionError) as caught:
        await invoke(helper, "alpine:latest", client=client, store=cache)
    assert caught.value is error
    assert not client.calls_for("get_operation_status")
    assert len(client.calls_for("cancel_operation")) == 1
    assert not (await invoke(cache.list_sessions)).items


@pytest.mark.parametrize("field", ["url", "project", "token"])
async def test_import_cache_connection_scope(mode, api, profile, field):
    helper = async_import_image if mode else sync_import_image
    for selected in [profile, replace(profile, **{field: "https://other.invalid" if field == "url" else "other"})]:
        await invoke(helper, "alpine:latest", profile=selected, client_type=api)
    assert all(len(c.calls_for("import_image")) == 1 for c in api.instances)


async def test_registry_credentials_scope(mode, api, profile):
    helper = async_import_image if mode else sync_import_image
    for password in ["one", "two"]:
        source = ImageImportRegistry(
            url="docker://registry.invalid/team/base:latest",
            credentials=ImageImportRegistryCredentials(username="user", password=password),
        )
        await invoke(helper, source, profile=profile, client_type=api)
    assert all(len(c.calls_for("import_image")) == 1 for c in api.instances)


@pytest.mark.parametrize("outcome", ["failed", "missing", "timeout"])
async def test_import_failure_is_not_cached_and_borrowed_client_remains_open(mode, api, outcome):
    client = api()
    client.mocks["wait_operation"].clear()
    if outcome == "timeout":
        client.mock("wait_operation", error=TimeoutError("wait failed"))
        error = TimeoutError
    else:
        response = operation_response(status=OperationStatus.FAILED if outcome == "failed" else OperationStatus.SUCCESS)
        client.mock("wait_operation", replace(response, result_image_uuid=None))
        error = FailedOperationError
    helper = async_import_image if mode else sync_import_image
    cache = AsyncMemoryStore() if mode else SyncMemoryStore()
    with pytest.raises(error):
        await invoke(helper, "alpine:latest", client=client, store=cache)
    assert not (await invoke(cache.list_sessions)).items
    assert client.closed == client.opened == 0
    assert len(client.calls_for("cancel_operation")) == (outcome == "timeout")


async def test_build_persists_layers_and_uploads_without_rebuilding(mode, api, profile, context, tmp_path):
    helper = async_build_image if mode else sync_build_image
    for _ in range(2):
        assert await invoke(helper, context, profile=profile, client_type=api, tag="app") == "built"
    first, second = api.instances
    assert len(first.calls_for("spawn_instance")) == 1
    assert not second.calls_for("spawn_instance")
    assert not second.calls_for("ensure_file")
    assert second.calls_for("update_image_tag")[0].args == ("built", "app")
    assert first.closed == second.closed == 1
    assert not (tmp_path / "xdg/contree/builds.sqlite3").exists()
    assert (tmp_path / "xdg/contree/images.sqlite3").is_file()


async def test_build_from_registry_waits_without_events(mode, api, context):
    client = api()
    client.mocks["resolve_image"].clear()
    client.mock("resolve_image", error=NotFoundError(404, "image not imported"))
    helper = async_build_image if mode else sync_build_image
    assert await invoke(helper, context, client=client) == "built"
    wait = client.calls_for("wait_operation")
    assert len(wait) == 1
    assert wait[0].args == ("import-1",)
    assert wait[0].kwargs == {"timeout": 600}


async def test_build_no_cache_bypasses_layers_but_reuses_uploads(mode, api, profile, context):
    helper = async_build_image if mode else sync_build_image
    await invoke(helper, context, profile=profile, client_type=api)
    await invoke(helper, context, profile=profile, client_type=api, no_cache=True)
    first, second = api.instances
    assert len(first.calls_for("spawn_instance")) == len(second.calls_for("spawn_instance")) == 1
    assert not second.calls_for("ensure_file")


async def test_build_scopes_default_history_by_connection(mode, api, profile, context):
    helper = async_build_image if mode else sync_build_image
    for selected in [profile, replace(profile, project="other")]:
        assert await invoke(helper, context, profile=selected, client_type=api) == "built"
    assert all(len(c.calls_for("spawn_instance")) == 1 for c in api.instances)


async def test_build_custom_components_and_builder_remain_caller_owned(mode, api, context):
    client = api()
    store = AsyncMemoryStore() if mode else SyncMemoryStore()

    class CustomBuilder(ContreeDockerBuilder):
        def __init__(self, client, *, marker, **kwargs):
            assert marker == "custom"
            super().__init__(client, **kwargs)

    class CustomAsyncBuilder(ContreeAsyncDockerBuilder):
        def __init__(self, client, *, marker, **kwargs):
            assert marker == "custom"
            super().__init__(client, **kwargs)

    options = {"marker": "custom", "store": None}
    helper = async_build_image if mode else sync_build_image
    assert (
        await invoke(
            helper,
            context,
            client=client,
            store=store,
            builder_type=CustomAsyncBuilder if mode else CustomBuilder,
            builder_kwargs=options,
            session_id="custom-build",
        )
        == "built"
    )
    assert client.closed == client.opened == 0
    assert options == {"marker": "custom", "store": None}
    assert await invoke(store.get_session, "custom-build")
    kinds = {info.kind for info in (await invoke(store.list_sessions)).items}
    assert {"docker-build", "upload-cache", "file-sources"} <= kinds
    await invoke(store.create_session, "after", kind="custom")
    assert (await invoke(store.get_session, "after")).kind == "custom"


async def test_build_failure_closes_owned_client(mode, api, profile, context):
    (context / "Dockerfile").write_text("INVALID\n")
    helper = async_build_image if mode else sync_build_image
    with pytest.raises(ValueError):
        await invoke(helper, context, profile=profile, client_type=api)
    assert api.instances[0].closed == 1


async def test_connection_sources_and_conflicts(mode, api, profile, monkeypatch, tmp_path):
    helper = async_import_image if mode else sync_import_image
    monkeypatch.setenv("CONTREE_URL", "https://env.invalid")
    monkeypatch.setenv("CONTREE_TOKEN", "env-token")
    monkeypatch.setenv("CONTREE_PROJECT", "env-project")
    await invoke(helper, "alpine:latest", client_type=api)
    assert api.instances[-1].project == "env-project"
    await invoke(helper, "alpine:latest", client_type=api, token="direct-token", project="direct-project")
    assert api.instances[-1].project == "direct-project"
    ini = tmp_path / "config.ini"
    ini.write_text(
        "[DEFAULT]\nprofile=local\n[profile:local]\ntype=iam\nurl=https://ini.invalid\ntoken=ini-token\nproject=ini-project\n"
    )
    await invoke(helper, "alpine:latest", client_type=api, config_path=ini)
    assert api.instances[-1].project == "ini-project"
    with pytest.raises(ValueError, match="cannot be combined"):
        await invoke(helper, "alpine:latest", client_type=api, profile=profile, token="other")
    with pytest.raises(ValueError, match="client cannot"):
        await invoke(helper, "alpine:latest", client=api(), profile=profile)


def test_xdg_fallback_and_explicit_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CACHE_HOME")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert image_cache_directory() == tmp_path / ".cache/contree"
    monkeypatch.setenv("XDG_CACHE_HOME", "relative")
    assert image_cache_directory() == tmp_path / ".cache/contree"
    assert image_cache_directory(tmp_path / "custom") == tmp_path / "custom"


async def test_async_import_cancellation_waits_for_cleanup(profile):
    started, closing, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class CancelClient(TrackingAsyncClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            del self.wait_operation

        async def wait_operation(self, *args, **kwargs):
            started.set()
            await asyncio.Future()

        async def close(self):
            closing.set()
            await release.wait()
            await super().close()

    task = asyncio.create_task(async_import_image("alpine:latest", profile=profile, client_type=CancelClient))
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    await asyncio.wait_for(closing.wait(), 1)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    client = TrackingAsyncClient.instances[-1]
    assert len(client.calls_for("cancel_operation")) == 1
    assert client.closed == 1


async def test_sync_and_async_helpers_share_persistent_cache(profile, context):
    assert sync_import_image("alpine:latest", profile=profile, client_type=TrackingClient) == "imported"
    assert await async_import_image("alpine:latest", profile=profile, client_type=TrackingAsyncClient) == "imported"
    assert not TrackingAsyncClient.instances[-1].calls_for("import_image")
    assert sync_build_image(context, profile=profile, client_type=TrackingClient) == "built"
    assert await async_build_image(context, profile=profile, client_type=TrackingAsyncClient) == "built"
    assert not TrackingAsyncClient.instances[-1].calls_for("spawn_instance")


@pytest.mark.parametrize("action", ["import", "build"])
@pytest.mark.parametrize("component", ["client", "store"])
async def test_helpers_reject_wrong_component_mode(mode, action, component, context):
    helpers = {
        (False, "import"): sync_import_image,
        (True, "import"): async_import_image,
        (False, "build"): sync_build_image,
        (True, "build"): async_build_image,
    }
    wrong = {
        "client": TrackingClient() if mode else TrackingAsyncClient(),
        "store": SyncMemoryStore() if mode else AsyncMemoryStore(),
    }
    with pytest.raises(TypeError, match=component):
        await invoke(
            helpers[mode, action], context if action == "build" else "alpine:latest", **{component: wrong[component]}
        )
