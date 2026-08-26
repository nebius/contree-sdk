import pytest
from contree_client.asyncio import ContreeAsyncClient
from contree_client.exceptions import ForbiddenError

from tests.e2e.conftest import TOKEN_FACTORY_SANDBOXES_URL


async def test_client_timeout(_contree_token: str):
    api = ContreeAsyncClient(_contree_token, base_url="http://127.0.0.1:9999", timeout=0.00001)
    with pytest.raises(TimeoutError):
        await api.list_images()


async def test_fake_token():
    api = ContreeAsyncClient("fake-token", base_url=TOKEN_FACTORY_SANDBOXES_URL)
    with pytest.raises(ForbiddenError):
        await api.list_images()
