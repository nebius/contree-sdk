import pytest

from contree_sdk import Contree
from contree_sdk.config import ContreeConfig
from contree_sdk.sdk.exceptions import ForbiddenError
from tests.e2e.sdk.test_client import test_client_timeout as _test_client_timeout
from tests.e2e.sdk.test_client import test_token_from_env_var as _test_token_from_env_var


async def test_fake_token(fake_contree_config: ContreeConfig):
    client = Contree(token="fake-token")
    with pytest.raises(ForbiddenError):
        await client.images()


async def test_client_timeout(fake_contree_config: ContreeConfig):
    await _test_client_timeout(fake_contree_config)


async def test_token_from_env_var(fake_token: str, monkeypatch, fake_contree_config: ContreeConfig, api_fake_images):
    await _test_token_from_env_var(fake_token, monkeypatch, fake_contree_config)
