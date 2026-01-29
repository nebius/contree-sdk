from dataclasses import replace

import pytest

from contree_sdk import Contree
from contree_sdk.config import ContreeConfig
from contree_sdk.sdk.exceptions import ApiTimeoutError, ForbiddenError


async def test_client_timeout(contree_config: ContreeConfig):
    config = replace(contree_config, transport_timeout=0.00001)

    client = Contree(config)
    with pytest.raises(ApiTimeoutError):
        await client.images()


async def test_fake_token(contree_config: ContreeConfig):
    config = replace(contree_config, token="fake-token")
    client = Contree(config)
    with pytest.raises(ForbiddenError):
        await client.images()


async def test_token_from_env_var(_contree_token: str, monkeypatch, contree_config: ContreeConfig):
    monkeypatch.setenv("CONTREE_TOKEN", _contree_token)
    config = ContreeConfig(base_url=contree_config.base_url)

    client = Contree(config=config)

    await client.images(number=1)
