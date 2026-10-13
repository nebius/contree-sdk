"""Connect the SDK abstractions through a simple, extensible sandbox interface.

ConTree's stateless execution model differs from a classic stateful sandbox:
filesystem state passes between executions through images and snapshots. This
module assembles clients, sessions, storage, caches, and policies to provide a
familiar sandbox workflow without requiring users to connect each component.

The default lazy session reuses a VM between commands. Snapshots preserve files,
but do not preserve running processes or memory. Advanced users can select or
extend session classes, supply components, and configure policies while keeping
control over execution, state, and resource ownership.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager, AbstractContextManager, AsyncExitStack, ExitStack, suppress
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Any, Generic, Literal, NoReturn, TypeVar, cast, overload

from contree_client import profiles
from contree_client.profiles import Profile
from contree_client.types import ContreeAsyncClient, ContreeSyncClient

from contree_sdk.cache import AsyncCache, CacheScope, SyncCache
from contree_sdk.cache.models import expiration
from contree_sdk.execution import AsyncExecutor, SyncExecutor
from contree_sdk.files import AsyncClientFileTransfer, AsyncFileTransfer, ClientFileTransfer, SyncFileTransfer
from contree_sdk.session.asyncio import ContreeAsyncSession
from contree_sdk.session.cleanup import await_cleanup
from contree_sdk.session.commit_policy import AbstractCommitPolicy
from contree_sdk.session.lazy_async import AsyncLazySession
from contree_sdk.session.lazy_sync import LazySession
from contree_sdk.session.sync import ContreeSession
from contree_sdk.store import AsyncMemoryStore, AsyncStore, SyncMemoryStore, SyncStore
from contree_sdk.upload_cache import AsyncCachedFileTransfer, CachedFileTransfer


SyncSessionT = TypeVar("SyncSessionT", bound=SyncExecutor)
AsyncSessionT = TypeVar("AsyncSessionT", bound=AsyncExecutor)
ContextT = TypeVar("ContextT")
Client = ContreeSyncClient | ContreeAsyncClient


def profile_from_args(
    *, token: str, url: str | None = None, project: str | None = None, auth_type: Literal["iam", "jwt"] = "jwt"
) -> Profile:
    """Build an explicit client profile without reading or writing configuration.

    IAM can use the client's default URL. JWT requires an explicit URL.

    Returns:
        A regular contree-client Profile.

    Raises:
        ValueError: Credentials, URL, or authentication type are invalid.

    """
    if auth_type not in {"iam", "jwt"}:
        raise ValueError("auth_type must be 'iam' or 'jwt'")
    if not token or not token.strip():
        raise ValueError("token must not be empty")
    if url is None and auth_type == "iam":
        url = profiles.DEFAULT_IAM_URL
    if not url or not url.strip():
        raise ValueError("url is required for JWT authentication")
    return Profile(name="explicit", url=url, token=token, project=project, auth_type=auth_type)


@dataclass
class SandboxConfig:
    image: str | None
    url: str | None = None
    project: str | None = None
    token: str | None = field(default=None, repr=False)
    auth_type: Literal["iam", "jwt"] | None = None
    profile: Profile | str | None = None
    config_path: str | Path | None = None
    session_type: type[SyncExecutor | AsyncExecutor] | None = None
    session_id: str | None = None
    storage: SyncStore | AsyncStore | None = None
    cache: SyncCache | AsyncCache | None = None
    cache_ttl: float = 60
    cwd: str | None = None
    env: dict[str, str] | None = None
    commit_policy: AbstractCommitPolicy | None = None
    file_transfer: SyncFileTransfer | AsyncFileTransfer | None = None
    session_kwargs: dict[str, Any] = field(default_factory=dict)
    client: Client | None = None
    client_type: type[ContreeSyncClient | ContreeAsyncClient] | None = None
    client_kwargs: dict[str, Any] = field(default_factory=dict, repr=False)

    def resolve_profile(self) -> Profile:
        if any(value is not None for value in (self.url, self.project, self.token, self.auth_type)):
            if self.profile is not None or self.config_path is not None:
                raise ValueError("connection arguments cannot be combined with profile or config_path")
            return profile_from_args(
                token=self.token or "", url=self.url, project=self.project, auth_type=self.auth_type or "jwt"
            )
        if isinstance(self.profile, Profile):
            if self.config_path is not None:
                raise ValueError("a Profile object cannot be combined with config_path")
            return self.profile
        if self.profile is not None or self.config_path is not None:
            return profiles.resolve_profile(self.profile, path=self.config_path)
        return profiles.from_env() or profiles.resolve_profile()

    def validate(self, *, asynchronous: bool) -> None:
        mode = "async with" if asynchronous else "with"
        if self.session_type is not None and (
            not isinstance(self.session_type, type)
            or not issubclass(self.session_type, AsyncExecutor if asynchronous else SyncExecutor)
        ):
            raise TypeError(f"session_type must be a compatible session class for {mode}")
        if self.client_type is not None and (
            not isinstance(self.client_type, type)
            or not issubclass(self.client_type, ContreeAsyncClient if asynchronous else ContreeSyncClient)
        ):
            raise TypeError(f"client_type must be a compatible client class for {mode}")
        if self.storage is not None and not isinstance(self.storage, AsyncStore if asynchronous else SyncStore):
            raise TypeError(f"storage must implement the store interface for {mode}")
        if self.cache is not None and not isinstance(self.cache, AsyncCache if asynchronous else SyncCache):
            raise TypeError(f"cache must implement the cache interface for {mode}")
        if self.file_transfer is not None and not isinstance(
            self.file_transfer, AsyncFileTransfer if asynchronous else SyncFileTransfer
        ):
            raise TypeError(f"file_transfer must implement the file transfer interface for {mode}")
        if self.client is not None and not isinstance(
            self.client, ContreeAsyncClient if asynchronous else ContreeSyncClient
        ):
            raise TypeError(f"client must implement the client interface for {mode}")
        if self.image is None and self.session_id is None:
            raise ValueError("either image or session_id must be provided")
        connection_values = (
            self.client_type,
            self.profile,
            self.config_path,
            self.url,
            self.project,
            self.token,
            self.auth_type,
        )
        if self.client is not None and (self.client_kwargs or any(value is not None for value in connection_values)):
            raise ValueError("client cannot be combined with client_type or connection settings")
        if "base_url" in self.client_kwargs:
            raise ValueError("use url or profile instead of base_url")
        expiration(self.cache_ttl, 0)

    def session_arguments(
        self, store: SyncStore | AsyncStore, transfer: SyncFileTransfer | AsyncFileTransfer
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        arguments = {
            "image": self.image,
            "session_id": self.session_id,
            "store": store,
            "file_transfer": transfer,
            "cwd": self.cwd,
            "env": self.env,
            "commit_policy": self.commit_policy,
        }
        kwargs = self.session_kwargs.copy()
        kwargs.pop("client", None)
        kwargs.pop("session", None)
        kwargs.pop("storage", None)
        kwargs.pop("cache", None)
        for name in arguments:
            kwargs.pop(name, None)
        return arguments, kwargs


class SyncSandboxSessionContext(Generic[SyncSessionT]):
    """Construct a synchronous session and unwind its owned resources."""

    def __init__(self, config: SandboxConfig) -> None:
        self.config = config
        self.stack = ExitStack()
        self._entered = False

    def _create(self) -> SyncExecutor:
        config, stack = self.config, self.stack
        client = cast("ContreeSyncClient | None", config.client)
        if client is None:
            client_type = cast("type[ContreeSyncClient] | None", config.client_type)
            if client_type is None:
                from contree_client.httpx import ContreeClient

                client_type = ContreeClient
            client = client_type.from_profile(config.resolve_profile(), **config.client_kwargs)
            stack.callback(client.close)
            client.open()
        store = cast("SyncStore | None", config.storage)
        if store is None:
            store = SyncMemoryStore()
            stack.callback(store.close)
        transfer = cast("SyncFileTransfer | None", config.file_transfer)
        if transfer is None:
            transfer = ClientFileTransfer(client)
        if config.cache is not None:
            transfer = CachedFileTransfer(
                transfer, cast("SyncCache", config.cache), scope=CacheScope.from_client(client), ttl=config.cache_ttl
            )
        session_type = cast("type[SyncExecutor]", config.session_type or LazySession)
        arguments, kwargs = config.session_arguments(store, transfer)
        if issubclass(session_type, LazySession):
            session = session_type(ContreeSession(client, **arguments), **kwargs)
        else:
            constructor = cast("Callable[..., SyncExecutor]", session_type)
            session = constructor(client, **arguments, **kwargs)
        if isinstance(session, AbstractContextManager):
            # Register cleanup before a custom context's entry can fail.
            stack.push(session)
            session.__enter__()  # noqa: PLC2801 - exit is registered before entry can fail
        return session

    def __enter__(self) -> SyncSessionT:
        if self._entered:
            raise RuntimeError("a sandbox context can only be entered once")
        self._entered = True
        self.config.validate(asynchronous=False)
        try:
            return cast("SyncSessionT", self._create())
        except BaseException:
            with suppress(Exception):
                self.stack.__exit__(*sys.exc_info())
            raise

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        if exc_type is None:
            self.stack.close()
        else:
            with suppress(Exception):
                self.stack.__exit__(exc_type, exc, tb)


class AsyncSandboxSessionContext(Generic[AsyncSessionT]):
    """Construct a native async session and join cleanup despite cancellation."""

    def __init__(self, config: SandboxConfig) -> None:
        self.config = config
        self.stack = AsyncExitStack()
        self._entered = False

    async def _create(self) -> AsyncExecutor:
        config, stack = self.config, self.stack
        client = cast("ContreeAsyncClient | None", config.client)
        if client is None:
            client_type = cast("type[ContreeAsyncClient] | None", config.client_type)
            if client_type is None:
                from contree_client.aiohttp import ContreeAsyncClient as AiohttpClient

                client_type = AiohttpClient
            client = client_type.from_profile(config.resolve_profile(), **config.client_kwargs)
            stack.push_async_callback(client.close)
            await client.open()
        store = cast("AsyncStore | None", config.storage)
        if store is None:
            store = AsyncMemoryStore()
            stack.push_async_callback(store.close)
        transfer = cast("AsyncFileTransfer | None", config.file_transfer)
        if transfer is None:
            transfer = AsyncClientFileTransfer(client)
        if config.cache is not None:
            transfer = AsyncCachedFileTransfer(
                transfer, cast("AsyncCache", config.cache), scope=CacheScope.from_client(client), ttl=config.cache_ttl
            )
        session_type = cast("type[AsyncExecutor]", config.session_type or AsyncLazySession)
        arguments, kwargs = config.session_arguments(store, transfer)
        if issubclass(session_type, AsyncLazySession):
            base = ContreeAsyncSession(client, **arguments)
            session = session_type(base, **kwargs)
        else:
            constructor = cast("Callable[..., AsyncExecutor]", session_type)
            session = constructor(client, **arguments, **kwargs)
            base = session if isinstance(session, ContreeAsyncSession) else None
        if isinstance(session, AbstractAsyncContextManager):
            # Register cleanup before a custom context's entry can fail.
            stack.push_async_exit(session)
            await session.__aenter__()  # noqa: PLC2801 - exit is registered before entry can fail
        if base is not None:
            await base.ensure_ready()
        return session

    async def __aenter__(self) -> AsyncSessionT:
        if self._entered:
            raise RuntimeError("a sandbox context can only be entered once")
        self._entered = True
        self.config.validate(asynchronous=True)
        try:
            return cast("AsyncSessionT", await self._create())
        except BaseException:
            with suppress(Exception, asyncio.CancelledError):
                await await_cleanup(self._unwind(*sys.exc_info()))
            raise

    async def _unwind(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self.stack.__aexit__(exc_type, exc, tb)

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        cleanup = self._unwind(exc_type, exc, tb)
        if exc_type is None:
            await await_cleanup(cleanup)
        else:
            with suppress(Exception, asyncio.CancelledError):
                await await_cleanup(cleanup)


class SandboxSessionContext(Generic[SyncSessionT, AsyncSessionT]):
    """Compose sync and async contexts with one shared, single-use boundary.

    Construction performs no I/O. Entry chooses the context mode explicitly.
    Re-entry, nesting, and switching modes on the same object are rejected.
    """

    def __init__(self, config: SandboxConfig) -> None:
        self._sync = SyncSandboxSessionContext[SyncSessionT](config)
        self._async = AsyncSandboxSessionContext[AsyncSessionT](config)
        self._entered = False

    def _begin(self) -> None:
        if self._entered:
            raise RuntimeError("a sandbox context can only be entered once")
        self._entered = True

    def __enter__(self) -> SyncSessionT:
        self._begin()
        return self._sync.__enter__()

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._sync.__exit__(exc_type, exc, tb)

    async def __aenter__(self) -> AsyncSessionT:
        self._begin()
        return await self._async.__aenter__()

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        await self._async.__aexit__(exc_type, exc, tb)


@overload
def create_sandbox_session(
    *,
    session_type: None = None,
    storage: SyncStore | AsyncStore | None = None,
    cache: SyncCache | AsyncCache | None = None,
    client: ContreeSyncClient | ContreeAsyncClient | None = None,
    client_type: type[ContreeSyncClient | ContreeAsyncClient] | None = None,
    file_transfer: SyncFileTransfer | AsyncFileTransfer | None = None,
    **kwargs: Any,
) -> SandboxSessionContext[LazySession, AsyncLazySession]: ...


@overload
def create_sandbox_session(
    *,
    session_type: type[SyncSessionT],
    storage: SyncStore | None = None,
    cache: SyncCache | None = None,
    client: ContreeSyncClient | None = None,
    client_type: type[ContreeSyncClient] | None = None,
    file_transfer: SyncFileTransfer | None = None,
    **kwargs: Any,
) -> SandboxSessionContext[SyncSessionT, NoReturn]: ...


@overload
def create_sandbox_session(
    *,
    session_type: type[AsyncSessionT],
    storage: AsyncStore | None = None,
    cache: AsyncCache | None = None,
    client: ContreeAsyncClient | None = None,
    client_type: type[ContreeAsyncClient] | None = None,
    file_transfer: AsyncFileTransfer | None = None,
    **kwargs: Any,
) -> SandboxSessionContext[NoReturn, AsyncSessionT]: ...


def create_sandbox_session(
    *, session_type: type[SyncExecutor | AsyncExecutor] | None = None, **kwargs: Any
) -> SandboxSessionContext[Any, Any]:
    """Create a single-use context supporting both with and async with.

    Returns:
        A composed context. See session_maker for all configuration parameters.

    """
    return session_maker(SandboxSessionContext, session_type=session_type, **kwargs)


@overload
def create_sync_sandbox_session(
    *,
    session_type: None = None,
    storage: SyncStore | None = None,
    cache: SyncCache | None = None,
    client: ContreeSyncClient | None = None,
    client_type: type[ContreeSyncClient] | None = None,
    file_transfer: SyncFileTransfer | None = None,
    **kwargs: Any,
) -> SyncSandboxSessionContext[LazySession]: ...


@overload
def create_sync_sandbox_session(
    *,
    session_type: type[SyncSessionT],
    storage: SyncStore | None = None,
    cache: SyncCache | None = None,
    client: ContreeSyncClient | None = None,
    client_type: type[ContreeSyncClient] | None = None,
    file_transfer: SyncFileTransfer | None = None,
    **kwargs: Any,
) -> SyncSandboxSessionContext[SyncSessionT]: ...


def create_sync_sandbox_session(
    *, session_type: type[SyncExecutor] | None = None, **kwargs: Any
) -> SyncSandboxSessionContext[Any]:
    """Create a sync-only context; its default session is LazySession.

    Returns:
        A synchronous context with the configuration accepted by session_maker.

    """
    return session_maker(SyncSandboxSessionContext, session_type=session_type, **kwargs)


@overload
def create_async_sandbox_session(
    *,
    session_type: None = None,
    storage: AsyncStore | None = None,
    cache: AsyncCache | None = None,
    client: ContreeAsyncClient | None = None,
    client_type: type[ContreeAsyncClient] | None = None,
    file_transfer: AsyncFileTransfer | None = None,
    **kwargs: Any,
) -> AsyncSandboxSessionContext[AsyncLazySession]: ...


@overload
def create_async_sandbox_session(
    *,
    session_type: type[AsyncSessionT],
    storage: AsyncStore | None = None,
    cache: AsyncCache | None = None,
    client: ContreeAsyncClient | None = None,
    client_type: type[ContreeAsyncClient] | None = None,
    file_transfer: AsyncFileTransfer | None = None,
    **kwargs: Any,
) -> AsyncSandboxSessionContext[AsyncSessionT]: ...


def create_async_sandbox_session(
    *, session_type: type[AsyncExecutor] | None = None, **kwargs: Any
) -> AsyncSandboxSessionContext[Any]:
    """Create an async-only context; its default session is AsyncLazySession.

    Returns:
        An asynchronous context with the configuration accepted by session_maker.

    """
    return session_maker(AsyncSandboxSessionContext, session_type=session_type, **kwargs)


def session_maker(  # noqa: PLR0913 - explicit routing of session, profile, and client settings
    context_type: Callable[[SandboxConfig], ContextT],
    /,
    *,
    image: str | None = None,
    url: str | None = None,
    project: str | None = None,
    token: str | None = None,
    auth_type: Literal["iam", "jwt"] | None = None,
    profile: Profile | str | None = None,
    config_path: str | Path | None = None,
    session_type: type[SyncExecutor | AsyncExecutor] | None = None,
    session_id: str | None = None,
    storage: SyncStore | AsyncStore | None = None,
    cache: SyncCache | AsyncCache | None = None,
    cache_ttl: float = 60,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    commit_policy: AbstractCommitPolicy | None = None,
    file_transfer: SyncFileTransfer | AsyncFileTransfer | None = None,
    session_kwargs: Mapping[str, Any] | None = None,
    client: Client | None = None,
    client_type: type[ContreeSyncClient | ContreeAsyncClient] | None = None,
    **client_kwargs: Any,
) -> ContextT:
    """Prepare a sync/async sandbox context without opening connections or a VM.

    Without session_type, entry selects LazySession or AsyncLazySession. Explicit
    classes must implement SyncExecutor or AsyncExecutor and match the context
    mode. Lazy subclasses receive a base session; other classes receive a client
    and the standard ContreeSession constructor keywords. session_kwargs adds
    arguments to the selected class, never to the underlying lazy base session.
    Factory-managed arguments take priority over duplicates in session_kwargs.

    Connection arguments, an explicit profile/config_path, and a borrowed client
    are separate sources. Without an explicit source, use the client's environment
    profile, then its default INI resolution. client_kwargs is forwarded unchanged
    to the selected client's from_profile constructor.

    The default lazy policy snapshots after 60 idle seconds. Normal exit saves
    pending work; exceptional exit discards unsaved work. Snapshots retain files,
    not running processes. Ordinary Session classes retain their existing commit
    and disposable defaults.

    Returns:
        A single-use context owning its created client, memory store, and session.
        Supplied clients, stores, caches, and file transfers remain caller-owned.

    """
    return context_type(
        SandboxConfig(
            image=image,
            url=url,
            project=project,
            token=token,
            auth_type=auth_type,
            profile=profile,
            config_path=config_path,
            session_type=session_type,
            session_id=session_id,
            storage=storage,
            cache=cache,
            cache_ttl=cache_ttl,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            commit_policy=commit_policy,
            file_transfer=file_transfer,
            session_kwargs=dict(session_kwargs or {}),
            client=client,
            client_type=client_type,
            client_kwargs=client_kwargs,
        )
    )
