import asyncio
import ssl
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from contree_client.models import FileResponse, StreamRepr
from contree_client.profiles import Profile, ProfileError
from contree_client.testing import ContreeAsyncClient as StubAsyncClient
from contree_client.testing import ContreeClient as StubClient

from contree_sdk import (
    AsyncLazySession,
    ContreeAsyncSession,
    ContreeSession,
    LazySession,
    RunRequest,
    create_async_sandbox_session,
    create_sandbox_session,
    create_sync_sandbox_session,
    profile_from_args,
)
from contree_sdk.cache import AsyncMemoryCache, CacheScope, SyncMemoryCache
from contree_sdk.files import AsyncClientFileTransfer, ClientFileTransfer, UploadFileSpec
from contree_sdk.session import IdleSnapshotPolicy, ManualSnapshotPolicy, ZeroExitCommitPolicy
from contree_sdk.store import AsyncMemoryStore, SyncMemoryStore
from contree_sdk.upload_cache import AsyncCachedFileTransfer, CachedFileTransfer
from tests.unit.session.lazy_clients import LiveAsyncClient, LiveClient


class FactoryClient(LiveClient):
    instances = []

    def __init__(self, token=None, **kwargs):
        super().__init__()
        StubClient.__init__(self, token or "test-token", **kwargs)
        self.mock("resolve_image", "base")
        self.opened = 0
        self.closed = 0
        self.instances.append(self)

    def open(self):
        self.opened += 1

    def close(self):
        self.closed += 1


class FactoryAsyncClient(LiveAsyncClient):
    instances = []

    def __init__(self, token=None, **kwargs):
        super().__init__()
        StubAsyncClient.__init__(self, token or "test-token", **kwargs)
        self.mock("resolve_image", "base")
        self.opened = 0
        self.closed = 0
        self.instances.append(self)

    async def open(self):
        self.opened += 1

    async def close(self):
        self.closed += 1


@pytest.fixture(autouse=True)
def isolated_connection(monkeypatch, tmp_path):
    for name in (
        "CONTREE_TOKEN",
        "NEBIUS_API_KEY",
        "CONTREE_URL",
        "CONTREE_PROJECT",
        "NEBIUS_AI_PROJECT",
        "CONTREE_PROFILE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CONTREE_HOME", str(tmp_path))
    FactoryClient.instances.clear()
    FactoryAsyncClient.instances.clear()


@pytest.fixture
def profile():
    return Profile(name="test", url="https://test.invalid", token="secret", auth_type="iam", project="project-1")


def test_default_sync_is_lazy_and_commits_once(profile):
    context = create_sandbox_session(image="base", profile=profile, client_type=FactoryClient)
    assert not FactoryClient.instances
    with context as session:
        assert type(session) is LazySession
        assert isinstance(session.snapshot_policy, IdleSnapshotPolicy)
        assert session.snapshot_policy.seconds == 10
        client = FactoryClient.instances[-1]
        assert client.opened == 1
        assert not client.calls_for("spawn_instance")
        first = session.run("first")
        second = session.run("second")
        assert isinstance(first.stdout, StreamRepr)
        assert isinstance(second.stdout, StreamRepr)
        assert first.stdout.as_text() == "first"
        assert second.stdout.as_text() == "second"
        assert len(client.calls_for("spawn_instance")) == 1
        store = session.session.store
        session_id = session.session_id
    assert len(store.history_dag(session_id)[0]) == 2
    assert session.phase == "closed"
    assert client.closed == 1
    with pytest.raises(RuntimeError, match="only be entered once"), context:
        pass


async def test_default_async_is_lazy_and_commits_once(profile):
    context = create_sandbox_session(image="base", profile=profile, client_type=FactoryAsyncClient)
    assert not FactoryAsyncClient.instances
    async with context as session:
        assert type(session) is AsyncLazySession
        assert isinstance(session.snapshot_policy, IdleSnapshotPolicy)
        assert session.snapshot_policy.seconds == 10
        client = FactoryAsyncClient.instances[-1]
        assert client.opened == 1
        assert not client.calls_for("spawn_instance")
        first = await session.run("first")
        second = await session.run("second")
        assert isinstance(first.stdout, StreamRepr)
        assert isinstance(second.stdout, StreamRepr)
        assert first.stdout.as_text() == "first"
        assert second.stdout.as_text() == "second"
        assert len(client.calls_for("spawn_instance")) == 1
        store = session.session.store
        session_id = session.session_id
    assert len((await store.history_dag(session_id))[0]) == 2
    assert session.phase == "closed"
    assert client.closed == 1
    with pytest.raises(RuntimeError, match="only be entered once"):
        async with context:
            pass


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_factory_configures_vm_without_a_custom_session(profile, asynchronous):
    api = FactoryAsyncClient if asynchronous else FactoryClient
    factory = create_async_sandbox_session if asynchronous else create_sync_sandbox_session
    vm = RunRequest(command="sleep", args=("7200",), timeout=3600, hostname="sandbox")
    context = factory(
        image="base",
        profile=profile,
        client_type=api,
        session_kwargs={"snapshot_policy": ManualSnapshotPolicy(), "vm_request": vm},
    )

    async def commands(session):
        assert type(session) is (AsyncLazySession if asynchronous else LazySession)
        for command in ("first", "second"):
            result = session.run(command)
            if asynchronous:
                await result
        client = api.instances[-1]
        starts = client.calls_for("spawn_instance")
        assert len(starts) == 1
        assert starts[0].args[0] == "sleep"
        assert starts[0].kwargs["timeout"] == 3600
        assert starts[0].kwargs["hostname"] == "sandbox"
        assert not session.snapshot_policy.should_snapshot().done()
        checkpoint = session.snapshot()
        if asynchronous:
            checkpoint = await checkpoint
        assert checkpoint.image_uuid == "image-op-1"
        result = session.run("third")
        if asynchronous:
            await result
        assert client.calls_for("spawn_instance")[1].args[1] == "image-op-1"

    if asynchronous:
        async with context as session:
            await commands(session)
    else:
        with context as session:
            await commands(session)
    assert api.instances[-1].closed == 1


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_custom_class_receives_components_and_options(profile, asynchronous):
    class CustomLazy(LazySession):
        def __init__(self, session, *, label, **kwargs):
            super().__init__(session, **kwargs)
            self.label = label

    class CustomAsyncLazy(AsyncLazySession):
        def __init__(self, session, *, label, **kwargs):
            super().__init__(session, **kwargs)
            self.label = label

    store = AsyncMemoryStore() if asynchronous else SyncMemoryStore()
    cache = AsyncMemoryCache() if asynchronous else SyncMemoryCache()
    store.close = AsyncMock() if asynchronous else Mock()
    cache.close = AsyncMock() if asynchronous else Mock()
    policy = IdleSnapshotPolicy(120)
    commit = ZeroExitCommitPolicy()
    selected = CustomAsyncLazy if asynchronous else CustomLazy
    options: dict[str, Any] = {
        "image": "base",
        "profile": profile,
        "client_type": FactoryAsyncClient if asynchronous else FactoryClient,
        "session_type": selected,
        "storage": store,
        "cache": cache,
        "session_id": "custom",
        "cwd": "/work",
        "env": {"A": "B"},
        "commit_policy": commit,
        "session_kwargs": {
            "label": "selected",
            "snapshot_policy": policy,
            "snapshot_timeout": 7,
            "client": None,
            "store": None,
            "cwd": "/ignored",
        },
    }
    original_kwargs = options["session_kwargs"].copy()
    context = create_sandbox_session(**options)
    if asynchronous:
        async with context as session:
            assert session.phase == "cold"
    else:
        with context as session:
            assert session.phase == "cold"
    assert type(session) is selected
    assert session.label == "selected"
    assert session.session_id == "custom"
    assert session.snapshot_policy is policy
    assert session.snapshot_timeout == 7
    assert session.session.store is store
    assert options["session_kwargs"] == original_kwargs
    assert isinstance(session.session.file_transfer, (CachedFileTransfer, AsyncCachedFileTransfer))
    assert session.session.file_transfer.cache.cache is cache
    assert session.session.commit_policy is commit
    assert session.session.cwd == "/work"
    assert session.session.env == {"A": "B"}
    store.close.assert_not_called()
    cache.close.assert_not_called()


@pytest.mark.parametrize("asynchronous", [False, True])
async def test_cache_reuses_uploads_and_borrowed_client_stays_open(asynchronous):
    if asynchronous:
        client = FactoryAsyncClient()
        cache = AsyncMemoryCache()
        transfer = AsyncClientFileTransfer(client)
    else:
        client = FactoryClient()
        cache = SyncMemoryCache()
        transfer = ClientFileTransfer(client)
    client.mock("ensure_file", FileResponse(uuid="upload", sha256="a" * 64, size=4))
    options: dict[str, Any] = {
        "image": "base",
        "client": client,
        "cache": cache,
        "file_transfer": transfer,
        "session_type": ContreeAsyncSession if asynchronous else ContreeSession,
    }
    file = UploadFileSpec(path="/input", source=b"same")
    if isinstance(cache, AsyncMemoryCache):
        async with create_sandbox_session(**options) as session:
            first = await session.upload_file(file)
            second = await session.upload_file(file)
        entries = await cache.entries(namespace=CacheScope.from_client(client).namespace("uploads"))
    else:
        with create_sandbox_session(**options) as session:
            first = session.upload_file(file)
            second = session.upload_file(file)
        entries = cache.entries(namespace=CacheScope.from_client(client).namespace("uploads"))
    assert first.uuid == second.uuid == "upload"
    assert len(client.calls_for("ensure_file")) == 1
    assert entries[0].expires_at is not None
    assert session.file_transfer.transfer is transfer
    assert client.opened == client.closed == 0


@pytest.mark.parametrize(
    "options",
    [
        {"session_type": AsyncLazySession},
        {"client_type": FactoryAsyncClient},
        {"storage": AsyncMemoryStore()},
        {"cache": AsyncMemoryCache()},
        {"file_transfer": AsyncClientFileTransfer(StubAsyncClient())},
        {"client": StubAsyncClient()},
    ],
)
def test_sync_rejects_async_components_before_creating_client(profile, options):
    with pytest.raises(TypeError, match="for with"), create_sandbox_session(image="base", **options):
        pass
    assert not FactoryClient.instances
    assert not FactoryAsyncClient.instances


@pytest.mark.parametrize(
    "options",
    [
        {"session_type": LazySession},
        {"client_type": FactoryClient},
        {"storage": SyncMemoryStore()},
        {"cache": SyncMemoryCache()},
        {"file_transfer": ClientFileTransfer(StubClient())},
        {"client": StubClient()},
    ],
)
async def test_async_rejects_sync_components_before_creating_client(options):
    with pytest.raises(TypeError, match="for async with"):
        async with create_sandbox_session(image="base", **options):
            pass
    assert not FactoryClient.instances
    assert not FactoryAsyncClient.instances


def test_explicit_profile_and_all_client_parameters(profile):
    tls = ssl.create_default_context()
    with create_sandbox_session(
        image="base",
        profile=profile,
        client_type=FactoryClient,
        timeout=12,
        identity="test/1",
        ssl_context=tls,
    ) as session:
        client = session.session.client
    assert isinstance(client, FactoryClient)
    assert client.constructed_with == {
        "token": profile.token,
        "base_url": profile.url,
        "project": profile.project,
        "timeout": 12,
        "retry": None,
        "identity": "test/1",
        "ssl_context": tls,
    }


@pytest.mark.parametrize(
    ("options", "expected_auth_type"),
    [({}, "iam"), ({"auth_type": "iam"}, "iam"), ({"auth_type": "jwt", "url": "https://test.invalid"}, "jwt")],
)
def test_direct_arguments_and_helper(monkeypatch, options, expected_auth_type):
    explicit = profile_from_args(token="token", project="project", **options)
    assert explicit.auth_type == expected_auth_type
    assert explicit.url.startswith("https://")
    factory = Mock(wraps=FactoryClient.from_profile)
    monkeypatch.setattr(FactoryClient, "from_profile", factory)
    with create_sandbox_session(
        image="base", token="token", project="project", client_type=FactoryClient, **options
    ) as session:
        assert factory.call_args.args[0].auth_type == expected_auth_type
        assert session.session.client.base_url == explicit.url
        assert session.session.client.project == "project"


@pytest.mark.parametrize("field", ["url", "token", "project", "auth_type"])
def test_profile_conflicts_with_any_explicit_connection_argument(profile, field):
    options: dict[str, Any] = {field: "value"}
    with (
        pytest.raises(ValueError, match="cannot be combined"),
        create_sandbox_session(image="base", profile=profile, client_type=FactoryClient, **options),
    ):
        pass
    assert not FactoryClient.instances


def test_environment_aliases_and_ini_precedence(monkeypatch, tmp_path, profile):
    ini = tmp_path / "config.ini"
    ini.write_text(
        "[DEFAULT]\nprofile=local\n[profile:local]\ntype=jwt\nurl=https://ini.invalid\ntoken=ini-token\nproject=ini-project\n"
    )
    monkeypatch.setenv("NEBIUS_API_KEY", "env-token")
    monkeypatch.setenv("CONTREE_URL", "https://env.invalid")
    monkeypatch.setenv("NEBIUS_AI_PROJECT", "env-project")
    with create_sandbox_session(image="base", client_type=FactoryClient) as session:
        assert session.session.client.token == "env-token"
        assert session.session.client.project == "env-project"
    with create_sandbox_session(image="base", config_path=ini, client_type=FactoryClient) as session:
        assert session.session.client.token == "ini-token"
    with create_sandbox_session(image="base", profile=profile, client_type=FactoryClient) as session:
        assert session.session.client.token == profile.token
    monkeypatch.delenv("NEBIUS_API_KEY")
    (tmp_path / "auth.ini").write_text(ini.read_text())
    with create_sandbox_session(image="base", client_type=FactoryClient) as session:
        assert session.session.client.token == "ini-token"
    with create_sandbox_session(image="base", profile="local", client_type=FactoryClient) as session:
        assert session.session.client.token == "ini-token"


@pytest.mark.parametrize(
    ("options", "error"),
    [
        ({"token": ""}, "token"),
        ({"token": "t", "auth_type": "jwt"}, "url"),
        ({"url": "https://test.invalid"}, "token"),
        ({"token": "t", "auth_type": "other"}, "auth_type"),
        ({"cache_ttl": -1}, "ttl"),
        ({"base_url": "https://test.invalid"}, "use url"),
        ({"client": StubClient(), "timeout": 5}, "client cannot"),
    ],
)
def test_invalid_configuration(options, error):
    with pytest.raises(ValueError, match=error), create_sandbox_session(image="base", **options):
        pass


def test_missing_profile_does_not_create_client():
    with pytest.raises(ProfileError), create_sandbox_session(image="base", client_type=FactoryClient):
        pass
    assert not FactoryClient.instances


def test_failed_session_constructor_closes_client(profile):
    with (
        pytest.raises(TypeError),
        create_sandbox_session(
            image="base", profile=profile, client_type=FactoryClient, session_kwargs={"invalid": True}
        ),
    ):
        pass
    assert FactoryClient.instances[-1].closed == 1


async def test_failed_async_client_open_closes_it(profile):
    class Broken(FactoryAsyncClient):
        async def open(self):
            raise ValueError("open failed")

    with pytest.raises(ValueError, match="open failed"):
        async with create_sandbox_session(image="base", profile=profile, client_type=Broken):
            pass
    assert FactoryAsyncClient.instances[-1].closed == 1


def test_body_error_aborts_before_closing_client(profile):
    with (  # noqa: PT012 - exercise exceptional context exit after starting a VM
        pytest.raises(ValueError, match="body failed"),
        create_sandbox_session(image="base", profile=profile, client_type=FactoryClient) as session,
    ):
        session.run("first")
        raise ValueError("body failed")
    client = FactoryClient.instances[-1]
    assert client.calls_for("cancel_operation")
    assert not client.calls_for("get_operation_status")
    assert client.closed == 1


def test_sync_only_factory_uses_the_same_configuration(profile):
    context = create_sync_sandbox_session(image="base", profile=profile, client_type=FactoryClient)
    assert not hasattr(context, "__aenter__")
    with context as session:
        assert isinstance(session, LazySession)
        session.run("one")
    with pytest.raises(RuntimeError, match="only be entered once"), context:
        pass


async def test_async_only_factory_uses_the_same_configuration(profile):
    context = create_async_sandbox_session(image="base", profile=profile, client_type=FactoryAsyncClient)
    assert not hasattr(context, "__enter__")
    async with context as session:
        assert isinstance(session, AsyncLazySession)
        await session.run("one")
    with pytest.raises(RuntimeError, match="only be entered once"):
        async with context:
            pass


async def test_composed_context_rejects_nested_and_mixed_entry(profile):
    context = create_sandbox_session(image="base", profile=profile, client_type=FactoryClient)
    with context, pytest.raises(RuntimeError, match="only be entered once"):
        async with context:
            pass
    with pytest.raises(RuntimeError, match="only be entered once"):
        async with context:
            pass
    assert len(FactoryClient.instances) == 1
    assert not FactoryAsyncClient.instances


async def test_cancelled_entry_closes_client_and_preserves_borrowed_store(profile):
    started = asyncio.Event()
    store = AsyncMemoryStore()
    store.close = AsyncMock()

    class WaitingSession(AsyncLazySession):
        async def __aenter__(self):
            started.set()
            await asyncio.Future()
            return self

    async def run():
        async with create_async_sandbox_session(
            image="base", profile=profile, client_type=FactoryAsyncClient, session_type=WaitingSession, storage=store
        ):
            pytest.fail("entry must not finish")

    task = asyncio.create_task(run())
    await asyncio.wait_for(started.wait(), 3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)
    assert FactoryAsyncClient.instances[-1].closed == 1
    store.close.assert_not_called()


def test_session_maker_accepts_custom_context_class(profile):
    from contree_sdk import session_maker
    from contree_sdk.sandbox import SyncSandboxSessionContext

    class Context(SyncSandboxSessionContext):
        pass

    context = session_maker(Context, image="base", profile=profile, client_type=FactoryClient)
    assert type(context) is Context
    with context as session:
        session.run("one")


def test_plain_session_subclass_preserves_request_hook(profile):
    from dataclasses import replace

    class PersistentSession(ContreeSession):
        def __init__(self, client, *, label, **kwargs):
            super().__init__(client, **kwargs)
            self.label = label

        def prepare_request(self, request):
            return super().prepare_request(replace(request, disposable=False))

    with create_sync_sandbox_session(
        image="base",
        profile=profile,
        client_type=FactoryClient,
        session_type=PersistentSession,
        session_kwargs={"label": "chosen"},
    ) as session:
        from contree_sdk import RunRequest

        assert type(session) is PersistentSession
        assert session.label == "chosen"
        assert session.prepare_request(RunRequest(command="echo")).disposable is False


def test_failed_custom_session_entry_runs_its_exit_before_client_close(profile):
    exits = []

    class BrokenEntry(LazySession):
        def __enter__(self):
            raise ValueError("entry failed")

        def __exit__(self, exc_type, exc, tb):
            assert isinstance(self.session.client, FactoryClient)
            exits.append((exc_type, self.session.client.closed))
            super().__exit__(exc_type, exc, tb)

    with (
        pytest.raises(ValueError, match="entry failed"),
        create_sync_sandbox_session(image="base", profile=profile, client_type=FactoryClient, session_type=BrokenEntry),
    ):
        pass
    assert exits == [(ValueError, 0)]
    assert FactoryClient.instances[-1].closed == 1


async def test_repeated_cancellation_joins_abort_and_client_close(profile):
    started = asyncio.Event()
    closing = asyncio.Event()
    release = asyncio.Event()

    class SlowClose(FactoryAsyncClient):
        async def close(self):
            closing.set()
            await release.wait()
            await super().close()

    async def run():
        async with create_sandbox_session(image="base", profile=profile, client_type=SlowClose) as session:
            await session.run("first")
            started.set()
            await asyncio.Future()

    task = asyncio.create_task(run())
    await asyncio.wait_for(started.wait(), 3)
    task.cancel()
    await asyncio.wait_for(closing.wait(), 3)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)
    client = FactoryAsyncClient.instances[-1]
    assert client.calls_for("cancel_operation")
    assert client.closed == 1
