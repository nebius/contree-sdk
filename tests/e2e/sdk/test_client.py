import pytest
from contree_client.asyncio import ContreeAsyncClient
from contree_client.exceptions import APIConnectionError, PermissionDeniedError

from tests.e2e.conftest import TOKEN_FACTORY_SANDBOXES_URL


async def test_client_timeout(_contree_token: str):
    api = ContreeAsyncClient(_contree_token, base_url="http://127.0.0.1:9999", timeout=0.00001)
    with pytest.raises(APIConnectionError) as exc:
        await api.list_images()
    assert exc.value.timed_out


async def test_fake_token():
    api = ContreeAsyncClient("fake-token", base_url=TOKEN_FACTORY_SANDBOXES_URL)
    with pytest.raises(PermissionDeniedError):
        await api.list_images()
