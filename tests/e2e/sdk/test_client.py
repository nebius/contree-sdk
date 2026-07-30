from dataclasses import replace

import pytest

from contree_sdk import Contree
from contree_sdk.auth import IAMAuth
from contree_sdk.config import ContreeConfig
from contree_sdk.sdk.exceptions import ApiTimeoutError, ForbiddenError


async def test_client_timeout(contree_config: ContreeConfig):
    config = replace(
        contree_config,
        auth=replace(contree_config.auth, base_url="http://127.0.0.1:9999"),
        transport_timeout=0.00001,
    )

    client = Contree(config)
    with pytest.raises(ApiTimeoutError):
        await client.images()


async def test_fake_token(contree_config: ContreeConfig):
    config = replace(contree_config, auth=replace(contree_config.auth, token="fake-token"))
    client = Contree(config)
    with pytest.raises(ForbiddenError):
        await client.images()


async def test_token_from_env_var(
    _contree_token: str, monkeypatch, contree_config: ContreeConfig, _contree_project_id: str
):
    monkeypatch.setenv("NEBIUS_API_KEY", _contree_token)
    monkeypatch.setenv("NEBIUS_PROJECT_ID", _contree_project_id)
    config = ContreeConfig(auth=IAMAuth(base_url=contree_config.auth.base_url), transport=contree_config.transport)

    client = Contree(config=config)

    await client.images(number=1)
