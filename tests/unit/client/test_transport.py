from collections.abc import Iterator
from dataclasses import replace

import pytest
from contree_client.base import ContreeAsyncClient, ContreeSyncClient
from contree_client.runtime import RequestSpec, ResponseData
from pytest_httpx import HTTPXMock

from contree_sdk import Contree, ContreeSync
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


def test_sync_facade_thread_mode_end_to_end(
    fake_contree_config: ContreeConfig, api_fake_whoami: HTTPXMock, token_uuid: str
):
    config = replace(fake_contree_config, sync_transport_mode="thread")

    token_info = ContreeSync(config=config).get_token_info()

    assert token_info.token_uuid == token_uuid
