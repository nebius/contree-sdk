from asyncio import get_running_loop, new_event_loop
from collections.abc import AsyncGenerator, Callable, Iterator
from dataclasses import replace
from typing import cast

import pytest
from contree_client.base import ContreeAsyncClient, ContreeSyncClient
from contree_client.runtime import RequestSpec, ResponseData
from pytest_httpx import HTTPXMock

from contree_sdk import Contree, ContreeSync
from contree_sdk._internals.client.provider import TranslatingClient
from contree_sdk._internals.client.transport import SyncTransportBridge, SyncTransportMode, resolve_transport_class
from contree_sdk.config import ContreeConfig


class StubSyncClient(ContreeSyncClient):
    UA_TRANSPORT_LIBRARY = "stub"
    retryable_errors = (ConnectionError,)
    nonretryable_errors = (TimeoutError,)

    def __init__(self) -> None:
        super().__init__("stub-token", base_url="https://stub.contree.endpoint")
        self.closed = False

    def request(self, spec: RequestSpec) -> ResponseData:
        return ResponseData(status=200, headers={}, body=b"ok")

    def stream(self, spec: RequestSpec, auto_decompress: bool = True) -> Iterator[bytes]:
        yield b"first"
        yield b"second"

    def close(self) -> None:
        self.closed = True


class StubAsyncClient(ContreeAsyncClient):
    UA_TRANSPORT_LIBRARY = "stub"
    retryable_errors = (ConnectionError,)
    nonretryable_errors = (TimeoutError,)

    def __init__(self) -> None:
        super().__init__("stub-token", base_url="https://stub.contree.endpoint")
        self.close_calls = 0
        self.on_close: Callable[[], None] | None = None

    async def request(self, spec: RequestSpec) -> ResponseData:
        return ResponseData(status=200, headers={}, body=b"ok")

    async def stream(self, spec: RequestSpec, auto_decompress: bool = True) -> AsyncGenerator[bytes, None]:
        yield b"first"

    async def close(self) -> None:
        self.close_calls += 1
        if self.on_close is not None:
            self.on_close()


@pytest.mark.parametrize("prefer_sync", [False, True])
def test_resolve_auto_matches_facade_flavor(prefer_sync: bool):
    transport_class = resolve_transport_class("auto", prefer_sync)

    expected_flavor = ContreeSyncClient if prefer_sync else ContreeAsyncClient
    assert issubclass(transport_class, expected_flavor)


@pytest.mark.parametrize(
    ("transport", "prefer_sync", "expected_flavor"),
    [
        ("httpx", False, ContreeAsyncClient),
        ("httpx", True, ContreeSyncClient),
        ("aiohttp", False, ContreeAsyncClient),
        ("aiohttp", True, ContreeAsyncClient),
        ("requests", False, ContreeSyncClient),
        ("requests", True, ContreeSyncClient),
        ("urllib3", False, ContreeSyncClient),
        ("http", False, ContreeSyncClient),
    ],
)
def test_resolve_named_transport(transport: str, prefer_sync: bool, expected_flavor: type):
    transport_class = resolve_transport_class(transport, prefer_sync)

    assert issubclass(transport_class, expected_flavor)
    assert not (issubclass(transport_class, ContreeSyncClient) and issubclass(transport_class, ContreeAsyncClient))


def test_resolve_unknown_transport_rejected():
    with pytest.raises(ValueError, match="unknown transport"):
        resolve_transport_class("carrier-pigeon", False)


@pytest.mark.parametrize("mode", ["thread", "blocking"])
async def test_bridge_request_and_stream(mode: SyncTransportMode):
    sync_client = StubSyncClient()
    bridge = SyncTransportBridge(sync_client, mode)

    response = await bridge.request(RequestSpec(method="GET", path="/whoami"))
    chunks = [chunk async for chunk in bridge.stream(RequestSpec(method="GET", path="/whoami"))]
    await bridge.close()

    assert response == ResponseData(status=200, headers={}, body=b"ok")
    assert chunks == [b"first", b"second"]
    assert sync_client.closed
    assert bridge.retryable_errors == (ConnectionError,)
    assert bridge.nonretryable_errors == (TimeoutError,)


def test_sync_facade_uses_blocking_sync_backend_by_default(fake_contree_config: ContreeConfig):
    provider = ContreeSync(config=fake_contree_config)._transport

    assert issubclass(provider._transport_class, ContreeSyncClient)
    assert provider._sync_transport_mode == "blocking"


def test_async_facade_uses_native_async_backend(fake_contree_config: ContreeConfig):
    provider = Contree(config=fake_contree_config)._transport

    assert issubclass(provider._transport_class, ContreeAsyncClient)


async def test_async_facade_context_closes_transport_before_eviction(fake_contree_config: ContreeConfig):
    contree = Contree(config=fake_contree_config)
    key = get_running_loop()
    transport = StubAsyncClient()
    translating_transport = cast(ContreeAsyncClient, TranslatingClient(transport))
    contree._transport._clients[key] = translating_transport

    def assert_transport_is_still_cached() -> None:
        assert contree._transport._clients.get(key) is translating_transport

    transport.on_close = assert_transport_is_still_cached

    async with contree as active:
        assert active is contree

    assert transport.close_calls == 1
    assert key not in contree._transport._clients

    await contree.aclose()
    assert transport.close_calls == 1


def test_sync_facade_context_closes_transport(fake_contree_config: ContreeConfig):
    contree = ContreeSync(config=fake_contree_config)
    transport = StubAsyncClient()
    contree._transport._clients[None] = transport

    with contree as active:
        assert active is contree

    assert transport.close_calls == 1
    assert None not in contree._transport._clients

    contree.close()
    assert transport.close_calls == 1


async def test_provider_prunes_clients_for_closed_event_loops(fake_contree_config: ContreeConfig, monkeypatch):
    provider = Contree(config=fake_contree_config)._transport
    stale_loop = new_event_loop()
    stale_transport = StubAsyncClient()
    current_transport = StubAsyncClient()
    stale_loop.close()
    provider._clients[stale_loop] = stale_transport
    monkeypatch.setattr(provider, "_create", lambda: current_transport)

    assert provider.get() is current_transport
    assert stale_loop not in provider._clients
    assert stale_transport.close_calls == 0

    await provider.aclose()


def test_sync_facade_thread_mode_end_to_end(
    fake_contree_config: ContreeConfig, api_fake_whoami: HTTPXMock, token_uuid: str
):
    config = replace(fake_contree_config, sync_transport_mode="thread")

    token_info = ContreeSync(config=config).get_token_info()

    assert token_info.token_uuid == token_uuid
