"""Import and build sandbox images with managed clients and persistent caches.

Each helper returns a ConTree image UUID for create_sandbox_session. Connection
settings follow the sandbox factory. Supplied clients, caches, and stores remain
caller-owned; helpers close only the resources they create.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from contree_client.models import ImageImportRegistry, OperationResponse, OperationStatus
from contree_client.profiles import Profile
from contree_client.types import ContreeAsyncClient, ContreeSyncClient

from contree_sdk.cache import AsyncCache, AsyncSQLiteCache, CacheScope, SyncCache, SyncSQLiteCache
from contree_sdk.cache.models import expiration
from contree_sdk.connection import ConnectionConfig, owned_resources, owned_resources_async
from contree_sdk.docker import BuildEvent, BuildStepEvent, ContreeAsyncDockerBuilder, ContreeDockerBuilder
from contree_sdk.docker.context import BUILD_TIMEOUT_DEFAULT
from contree_sdk.docker.kw_from import normalize_registry_url
from contree_sdk.docker.parser import make_session_key
from contree_sdk.exceptions import FailedOperationError
from contree_sdk.session.cleanup import await_cleanup
from contree_sdk.store import AsyncSQLiteStore, AsyncStore, SyncSQLiteStore, SyncStore


IMPORT_CACHE_TTL = 3600


def image_cache_directory(cache_dir: str | Path | None = None) -> Path:
    """Select the image cache directory without creating it.

    Returns:
        The explicit directory or $XDG_CACHE_HOME/contree (default ~/.cache/contree).

    """
    if cache_dir is not None:
        return Path(cache_dir).expanduser()
    configured = os.environ.get("XDG_CACHE_HOME")
    root = Path(configured) if configured else Path.home() / ".cache"
    if not root.is_absolute():
        root = Path.home() / ".cache"
    return root / "contree"


def _registry(source: str | ImageImportRegistry) -> ImageImportRegistry:
    if isinstance(source, ImageImportRegistry):
        return source
    if not source.strip():
        raise ValueError("image source must not be empty")
    return ImageImportRegistry(url=normalize_registry_url(source))


def _import_key(registry: ImageImportRegistry, tag: str | None) -> str:
    # Hash registry credentials as well; never persist them in keys or records.
    value = json.dumps([asdict(registry), tag], sort_keys=True, default=repr)
    return hashlib.sha256(value.encode()).hexdigest()


def _import_result(operation_id: str, response: OperationResponse) -> str:
    if (
        response.status != OperationStatus.SUCCESS
        or not isinstance(response.result_image_uuid, str)
        or not response.result_image_uuid
    ):
        error = response.error if isinstance(response.error, str) else "image import produced no image"
        raise FailedOperationError(operation_id, error)
    return response.result_image_uuid


def sync_import_image(  # noqa: PLR0913 - explicit connection and import options
    source: str | ImageImportRegistry,
    *,
    tag: str | None = None,
    timeout: int = 300,
    no_cache: bool = False,
    cache: SyncCache | None = None,
    cache_dir: str | Path | None = None,
    cache_ttl: float = IMPORT_CACHE_TTL,
    url: str | None = None,
    project: str | None = None,
    token: str | None = None,
    auth_type: Literal["iam", "jwt"] | None = None,
    profile: Profile | str | None = None,
    config_path: str | Path | None = None,
    client: ContreeSyncClient | None = None,
    client_type: type[ContreeSyncClient] | None = None,
    **client_kwargs: Any,
) -> str:
    """Import a registry image and wait for a usable filesystem image.

    Registry names such as alpine:latest and docker:// URLs are accepted. Pass
    ImageImportRegistry for registry credentials. Results are cached for one
    hour by default. no_cache=True imports again and refreshes the cached result.
    A requested tag is reapplied on cache hits. Timeout or interruption after
    submission requests cancellation of the import operation. Import failure or
    a missing result image raises FailedOperationError. Imports poll operation
    status with follow_events=False because image imports do not provide events.

    Returns:
        The imported ConTree image UUID.

    Raises:
        TypeError: A supplied component uses the wrong execution mode.
        ValueError: The source, timeout, TTL, or connection settings are invalid.

    """
    registry = _registry(source)
    expiration(cache_ttl, 0)
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if cache is not None and not isinstance(cache, SyncCache):
        raise TypeError("cache must implement SyncCache")
    connection = ConnectionConfig(
        url=url,
        project=project,
        token=token,
        auth_type=auth_type,
        profile=profile,
        config_path=config_path,
        client=client,
        client_type=client_type,
        client_kwargs=client_kwargs,
    )
    with owned_resources() as stack:
        active_client = connection.open_sync(stack)
        active_cache = cache
        if active_cache is None:
            active_cache = SyncSQLiteCache(image_cache_directory(cache_dir) / "images.sqlite3")
            stack.callback(active_cache.close)
        namespace = CacheScope.from_client(active_client).namespace("image-import")
        key = _import_key(registry, tag)
        if not no_cache:
            cached = active_cache.get(key, namespace=namespace)
            if isinstance(cached, str) and cached:
                if tag is not None:
                    active_client.update_image_tag(cached, tag)
                return cached
        operation_id = active_client.import_image(registry, tag=tag, timeout=timeout)
        try:
            response = active_client.wait_operation(operation_id, timeout=timeout, follow_events=False)
        except BaseException:
            with suppress(Exception):
                active_client.cancel_operation(operation_id)
            raise
        image_uuid = _import_result(operation_id, response)
        active_cache.set(key, image_uuid, namespace=namespace, ttl=cache_ttl)
        return image_uuid


async def async_import_image(  # noqa: PLR0913 - explicit connection and import options
    source: str | ImageImportRegistry,
    *,
    tag: str | None = None,
    timeout: int = 300,
    no_cache: bool = False,
    cache: AsyncCache | None = None,
    cache_dir: str | Path | None = None,
    cache_ttl: float = IMPORT_CACHE_TTL,
    url: str | None = None,
    project: str | None = None,
    token: str | None = None,
    auth_type: Literal["iam", "jwt"] | None = None,
    profile: Profile | str | None = None,
    config_path: str | Path | None = None,
    client: ContreeAsyncClient | None = None,
    client_type: type[ContreeAsyncClient] | None = None,
    **client_kwargs: Any,
) -> str:
    """Import a registry image and wait for a usable filesystem image.

    Registry names such as alpine:latest and docker:// URLs are accepted. Pass
    ImageImportRegistry for registry credentials. Results are cached for one
    hour by default. no_cache=True imports again and refreshes the cached result.
    A requested tag is reapplied on cache hits. Timeout or interruption after
    submission requests cancellation of the import operation. Import failure or
    a missing result image raises FailedOperationError. Imports poll operation
    status with follow_events=False because image imports do not provide events.

    Returns:
        The imported ConTree image UUID.

    Raises:
        TypeError: A supplied component uses the wrong execution mode.
        ValueError: The source, timeout, TTL, or connection settings are invalid.

    """
    registry = _registry(source)
    expiration(cache_ttl, 0)
    if timeout <= 0:
        raise ValueError("timeout must be positive")
    if cache is not None and not isinstance(cache, AsyncCache):
        raise TypeError("cache must implement AsyncCache")
    connection = ConnectionConfig(
        url=url,
        project=project,
        token=token,
        auth_type=auth_type,
        profile=profile,
        config_path=config_path,
        client=client,
        client_type=client_type,
        client_kwargs=client_kwargs,
    )
    async with owned_resources_async() as stack:
        active_client = await connection.open_async(stack)
        active_cache = cache
        if active_cache is None:
            active_cache = AsyncSQLiteCache(image_cache_directory(cache_dir) / "images.sqlite3")
            stack.push_async_callback(active_cache.close)
        namespace = CacheScope.from_client(active_client).namespace("image-import")
        key = _import_key(registry, tag)
        if not no_cache:
            cached = await active_cache.get(key, namespace=namespace)
            if isinstance(cached, str) and cached:
                if tag is not None:
                    await active_client.update_image_tag(cached, tag)
                return cached
        operation_id = await active_client.import_image(registry, tag=tag, timeout=timeout)
        try:
            response = await active_client.wait_operation(operation_id, timeout=timeout, follow_events=False)
        except BaseException:
            with suppress(Exception, asyncio.CancelledError):
                await await_cleanup(active_client.cancel_operation(operation_id))
            raise
        image_uuid = _import_result(operation_id, response)
        await active_cache.set(key, image_uuid, namespace=namespace, ttl=cache_ttl)
        return image_uuid


def sync_build_image(  # noqa: PLR0913 - explicit connection and build options
    context: str | Path,
    *,
    dockerfile: str | Path | None = None,
    tag: str | None = None,
    build_args: dict[str, str] | None = None,
    no_cache: bool = False,
    timeout: int = BUILD_TIMEOUT_DEFAULT,
    session_id: str | None = None,
    storage: SyncStore | None = None,
    cache: SyncCache | None = None,
    cache_dir: str | Path | None = None,
    on_event: Callable[[BuildEvent], None] | None = None,
    on_step: Callable[[BuildStepEvent], None] | None = None,
    builder_type: type[ContreeDockerBuilder] = ContreeDockerBuilder,
    builder_kwargs: Mapping[str, Any] | None = None,
    url: str | None = None,
    project: str | None = None,
    token: str | None = None,
    auth_type: Literal["iam", "jwt"] | None = None,
    profile: Profile | str | None = None,
    config_path: str | Path | None = None,
    client: ContreeSyncClient | None = None,
    client_type: type[ContreeSyncClient] | None = None,
    **client_kwargs: Any,
) -> str:
    """Build a Dockerfile with persistent layer history and upload caching.

    The default Dockerfile is context/Dockerfile. Native SQLite store and cache
    instances are opened in the XDG cache directory unless supplied explicitly.
    no_cache=True disables layer reuse; content-addressed uploads remain cached.
    Use builder_type and builder_kwargs to extend the existing Docker builder.
    The connection scope is part of the default build session identity.
    Invalid inputs raise ValueError; failed build steps raise DockerBuildError.

    Returns:
        The built ConTree filesystem image UUID.

    Raises:
        TypeError: A supplied component uses the wrong execution mode.

    """
    if storage is not None and not isinstance(storage, SyncStore):
        raise TypeError("storage must implement SyncStore")
    if cache is not None and not isinstance(cache, SyncCache):
        raise TypeError("cache must implement SyncCache")
    if not isinstance(builder_type, type) or not issubclass(builder_type, ContreeDockerBuilder):
        raise TypeError("builder_type must extend ContreeDockerBuilder")
    connection = ConnectionConfig(
        url=url,
        project=project,
        token=token,
        auth_type=auth_type,
        profile=profile,
        config_path=config_path,
        client=client,
        client_type=client_type,
        client_kwargs=client_kwargs,
    )
    options = dict(builder_kwargs or {})
    for name in ("client", "store", "cache"):
        options.pop(name, None)
    with owned_resources() as stack:
        active_client = connection.open_sync(stack)
        directory = image_cache_directory(cache_dir)
        active_store = storage
        if active_store is None:
            active_store = SyncSQLiteStore(directory / "builds.sqlite3")
            stack.callback(active_store.close)
        active_cache = cache
        if active_cache is None:
            active_cache = SyncSQLiteCache(directory / "images.sqlite3")
            stack.callback(active_cache.close)
        selected_id = session_id
        if selected_id is None:
            resolved = Path(context).resolve()
            selected_id = f"{make_session_key(resolved)}:{CacheScope.from_client(active_client).digest}"
        builder = builder_type(active_client, store=active_store, cache=active_cache, **options)
        return builder.build(
            context,
            dockerfile=dockerfile,
            tag=tag,
            build_args=build_args,
            no_cache=no_cache,
            timeout=timeout,
            session_id=selected_id,
            on_event=on_event,
            on_step=on_step,
        )


async def async_build_image(  # noqa: PLR0913 - explicit connection and build options
    context: str | Path,
    *,
    dockerfile: str | Path | None = None,
    tag: str | None = None,
    build_args: dict[str, str] | None = None,
    no_cache: bool = False,
    timeout: int = BUILD_TIMEOUT_DEFAULT,
    session_id: str | None = None,
    storage: AsyncStore | None = None,
    cache: AsyncCache | None = None,
    cache_dir: str | Path | None = None,
    on_event: Callable[[BuildEvent], object] | None = None,
    on_step: Callable[[BuildStepEvent], object] | None = None,
    builder_type: type[ContreeAsyncDockerBuilder] = ContreeAsyncDockerBuilder,
    builder_kwargs: Mapping[str, Any] | None = None,
    url: str | None = None,
    project: str | None = None,
    token: str | None = None,
    auth_type: Literal["iam", "jwt"] | None = None,
    profile: Profile | str | None = None,
    config_path: str | Path | None = None,
    client: ContreeAsyncClient | None = None,
    client_type: type[ContreeAsyncClient] | None = None,
    **client_kwargs: Any,
) -> str:
    """Build a Dockerfile with persistent layer history and upload caching.

    The default Dockerfile is context/Dockerfile. Native SQLite store and cache
    instances are opened in the XDG cache directory unless supplied explicitly.
    no_cache=True disables layer reuse; content-addressed uploads remain cached.
    Use builder_type and builder_kwargs to extend the existing Docker builder.
    The connection scope is part of the default build session identity.
    Invalid inputs raise ValueError; failed build steps raise DockerBuildError.

    Returns:
        The built ConTree filesystem image UUID.

    Raises:
        TypeError: A supplied component uses the wrong execution mode.

    """
    if storage is not None and not isinstance(storage, AsyncStore):
        raise TypeError("storage must implement AsyncStore")
    if cache is not None and not isinstance(cache, AsyncCache):
        raise TypeError("cache must implement AsyncCache")
    if not isinstance(builder_type, type) or not issubclass(builder_type, ContreeAsyncDockerBuilder):
        raise TypeError("builder_type must extend ContreeAsyncDockerBuilder")
    connection = ConnectionConfig(
        url=url,
        project=project,
        token=token,
        auth_type=auth_type,
        profile=profile,
        config_path=config_path,
        client=client,
        client_type=client_type,
        client_kwargs=client_kwargs,
    )
    options = dict(builder_kwargs or {})
    for name in ("client", "store", "cache"):
        options.pop(name, None)
    async with owned_resources_async() as stack:
        active_client = await connection.open_async(stack)
        directory = image_cache_directory(cache_dir)
        active_store = storage
        if active_store is None:
            active_store = AsyncSQLiteStore(directory / "builds.sqlite3")
            stack.push_async_callback(active_store.close)
        active_cache = cache
        if active_cache is None:
            active_cache = AsyncSQLiteCache(directory / "images.sqlite3")
            stack.push_async_callback(active_cache.close)
        selected_id = session_id
        if selected_id is None:
            resolved = await asyncio.to_thread(Path(context).resolve)
            selected_id = f"{make_session_key(resolved)}:{CacheScope.from_client(active_client).digest}"
        builder = builder_type(active_client, store=active_store, cache=active_cache, **options)
        return await builder.build(
            context,
            dockerfile=dockerfile,
            tag=tag,
            build_args=build_args,
            no_cache=no_cache,
            timeout=timeout,
            session_id=selected_id,
            on_event=on_event,
            on_step=on_step,
        )
