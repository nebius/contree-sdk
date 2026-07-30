from __future__ import annotations

from asyncio import sleep, to_thread
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterator
from importlib import import_module
from typing import Any, Literal, get_args

from contree_client.base import ContreeAsyncClient, ContreeSyncClient
from contree_client.runtime import RequestSpec, ResponseData


TransportName = Literal["auto", "aiohttp", "httpx", "requests", "urllib3", "http"]
SyncTransportMode = Literal["thread", "blocking"]
TransportClass = type[ContreeSyncClient] | type[ContreeAsyncClient]

_BACKEND_NAMES = tuple(name for name in get_args(TransportName) if name != "auto")


def _next_chunk(chunks: Iterator[bytes]) -> bytes | None:
    for chunk in chunks:
        return chunk
    return None


async def _run_blocking(func: Callable[..., Any], /, *args: Any) -> Any:
    await sleep(0)
    try:
        return func(*args)
    finally:
        await sleep(0)


class SyncTransportBridge(ContreeAsyncClient):
    """Exposes a synchronous contree-client backend through the async interface.

    Every blocking call goes through a single mode-selected wrapper: ``thread``
    runs it in a worker thread, ``blocking`` runs it directly on the event loop
    between ``await sleep(0)`` suspension points — threads are not used, the
    client blocks for the duration of each call, and other tasks on the same
    loop only progress between calls. Blocking is the expected behavior for
    the synchronous SDK facade.
    """

    def __init__(self, sync_client: ContreeSyncClient, mode: SyncTransportMode) -> None:
        super().__init__(
            sync_client.token,
            base_url=sync_client.base_url,
            project=sync_client.project,
            timeout=sync_client.timeout,
            retry=sync_client.retry,
            identity=sync_client.identity,
        )
        self.retryable_errors = type(sync_client).retryable_errors
        self.nonretryable_errors = type(sync_client).nonretryable_errors
        self._sync_client = sync_client
        self._call: Callable[..., Awaitable[Any]] = _run_blocking if mode == "blocking" else to_thread

    async def request(self, spec: RequestSpec) -> ResponseData:
        return await self._call(self._sync_client.request, spec)

    async def stream(self, spec: RequestSpec, auto_decompress: bool = True) -> AsyncGenerator[bytes, None]:
        chunks = self._sync_client.stream(spec, auto_decompress)
        try:
            while (chunk := await self._call(_next_chunk, chunks)) is not None:
                yield chunk
        finally:
            close = getattr(chunks, "close", None)
            if close is not None:
                await self._call(close)

    async def close(self) -> None:
        await self._call(self._sync_client.close)


def resolve_transport_class(transport: TransportName | str, prefer_sync: bool) -> TransportClass:
    """Resolve a transport name to a contree-client backend class.

    ``auto`` reuses contree-client's own backend autodetection: the
    synchronous ladder for the sync SDK facade and the asynchronous ladder
    (falling back to the synchronous one) for the async facade. An explicit
    backend name picks the flavor matching the facade when the backend
    provides both.

    Returns:
        The contree-client backend class to instantiate.

    Raises:
        ValueError: If the transport name is not a known backend.
        ImportError: If the backend package is not installed.

    """
    if transport == "auto":
        return _autodetect_class(prefer_sync)
    if transport not in _BACKEND_NAMES:
        raise ValueError(f"unknown transport {transport!r}, expected 'auto' or one of {_BACKEND_NAMES}")
    module = _backend_module(transport)
    flavors = ("ContreeClient", "ContreeAsyncClient") if prefer_sync else ("ContreeAsyncClient", "ContreeClient")
    for flavor in flavors:
        transport_class: TransportClass | None = getattr(module, flavor, None)
        if transport_class is not None:
            return transport_class
    raise ImportError(f"transport module contree_client.{transport} exposes no client class")


def _autodetect_class(prefer_sync: bool) -> TransportClass:
    if not prefer_sync:
        try:
            from contree_client.asyncio import detect_backend
        except ImportError:
            pass
        else:
            return detect_backend()[1]
    from contree_client.sync import detect_backend

    return detect_backend()[1]


def _backend_module(name: str) -> Any:
    try:
        return import_module(f"contree_client.{name}")
    except ModuleNotFoundError as exc:
        if exc.name not in {name, f"contree_client.{name}"}:
            raise
        raise ImportError(f"the {name!r} transport requires the {name} package; install contree-sdk[{name}]") from exc
