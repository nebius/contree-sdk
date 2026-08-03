from contree_sdk.config import ContreeConfig
from tests.e2e.sdk.test_client import test_client_timeout as _test_client_timeout
from tests.e2e.sdk.test_client import test_fake_token as _test_fake_token
from tests.e2e.sdk.test_client import test_token_from_env_var as _test_token_from_env_var


async def test_client_timeout(fake_contree_config: ContreeConfig):
    await _test_client_timeout(fake_contree_config)


async def test_fake_token(fake_contree_config: ContreeConfig, api_fake_forbidden):
    await _test_fake_token(fake_contree_config)


async def test_token_from_env_var(
    fake_token: str, monkeypatch, fake_contree_config: ContreeConfig, api_fake_images, fake_project_id
):
    await _test_token_from_env_var(fake_token, monkeypatch, fake_contree_config, fake_project_id)
