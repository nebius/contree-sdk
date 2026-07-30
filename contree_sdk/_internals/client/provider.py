from __future__ import annotations

from asyncio import get_running_loop
from contextlib import aclosing
from functools import wraps
from inspect import isasyncgenfunction, iscoroutinefunction
from typing import Any, cast

from contree_client.base import ContreeAsyncClient, ContreeSyncClient

from contree_sdk._internals.client.transport import (
    SyncTransportBridge,
    SyncTransportMode,
    TransportName,
    resolve_transport_class,
)
from contree_sdk._internals.utils.config import build_user_agent
from contree_sdk._internals.utils.exception import wrap_api_call
from contree_sdk.auth import IAMAuth, JWTAuth


class TranslatingClient:
    """Duck-typed ``ContreeAsyncClient`` raising SDK exceptions.

    contree-client raises its own exception hierarchy from inside the
    generated API methods, so every coroutine and async-generator method is
    wrapped with :func:`wrap_api_call`; resolved wrappers are cached on the
    instance, everything else passes through untouched.
    """

    def __init__(self, inner: ContreeAsyncClient) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if iscoroutinefunction(attr):
            wrapper = self._wrap_coroutine(attr)
        elif isasyncgenfunction(attr):
            wrapper = self._wrap_generator(attr)
        else:
            return attr
        setattr(self, name, wrapper)
        return wrapper

    def _wrap_coroutine(self, method: Any) -> Any:
        @wraps(method)
        async def call(*args: Any, **kwargs: Any) -> Any:
            with wrap_api_call(self._inner):
                return await method(*args, **kwargs)

        return call

    def _wrap_generator(self, method: Any) -> Any:
        @wraps(method)
        async def iterate(*args: Any, **kwargs: Any) -> Any:
            events = method(*args, **kwargs)
            async with aclosing(events):
                while True:
                    with wrap_api_call(self._inner):
                        try:
                            item = await anext(events)
                        except StopAsyncIteration:
                            return
                    yield item  # noqa: ASYNC119

        return iterate


class TransportProvider:
    """Lazily creates and caches contree-client transports.

    Asynchronous backends are bound to an event loop, so they are created
    per running loop; synchronous backends are shared behind a
    :class:`SyncTransportBridge`. Every transport is wrapped in a
    :class:`TranslatingClient` so it raises SDK exceptions.
    """

    def __init__(
        self,
        auth: IAMAuth | JWTAuth,
        transport_timeout: float = 10.0,
        transport: TransportName = "auto",
        sync_transport_mode: SyncTransportMode = "thread",
        prefer_sync_transport: bool = False,
    ) -> None:
        self._transport_class = resolve_transport_class(transport, prefer_sync_transport)
        self._sync_transport_mode: SyncTransportMode = sync_transport_mode
        self._auth = auth
        self._transport_timeout = transport_timeout
        self._identity = build_user_agent()
        self._clients: dict[object, ContreeAsyncClient] = {}

    def get(self) -> ContreeAsyncClient:
        key = None if issubclass(self._transport_class, ContreeSyncClient) else get_running_loop()
        client = self._clients.get(key)
        if client is None:
            client = self._clients[key] = self._create()
        return client

    def _create(self) -> ContreeAsyncClient:
        client = self._transport_class(
            self._auth.token,
            base_url=self._auth.base_url,
            project=getattr(self._auth, "project_id", None),
            timeout=self._transport_timeout,
            identity=self._identity,
        )
        if isinstance(client, ContreeSyncClient):
            client = SyncTransportBridge(client, self._sync_transport_mode)
        return cast("ContreeAsyncClient", TranslatingClient(client))
