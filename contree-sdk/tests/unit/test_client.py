from dataclasses import replace

import pytest

from contree_sdk import ContreeSync
from contree_sdk.config import ContreeConfig
from tests.e2e.sdk.test_client import test_client_timeout as _test_client_timeout
from tests.e2e.sdk.test_client import test_fake_token as _test_fake_token
from tests.e2e.sdk.test_client import test_token_from_env_var as _test_token_from_env_var


async def test_client_timeout(fake_contree_config: ContreeConfig):
    await _test_client_timeout(fake_contree_config)


async def test_fake_token(fake_contree_config: ContreeConfig, api_fake_forbidden):
    await _test_fake_token(fake_contree_config)


async def test_token_from_env_var(fake_token: str, monkeypatch, fake_contree_config: ContreeConfig, api_fake_images):
    await _test_token_from_env_var(fake_token, monkeypatch, fake_contree_config)


@pytest.mark.parametrize(
    "config,progress_ratio,expected_range",
    [
        (ContreeConfig(), 0.0, (0.1, 0.15)),
        (ContreeConfig(), 0.25, (4.0, 5.0)),
        (ContreeConfig(), 0.5, (6.5, 7.5)),
        (ContreeConfig(), 0.75, (8.0, 9.0)),
        (ContreeConfig(), 1.0, (9.5, 10.0)),
        (
            ContreeConfig(operation_poll_secs_min=1.0, operation_poll_secs_max=5.0),
            0.5,
            (3.5, 4.0),
        ),
        (
            ContreeConfig(operation_poll_secs_min=0.5, operation_poll_secs_max=20.0),
            0.5,
            (13.0, 14.5),
        ),
    ],
)
def test_get_interval(config: ContreeConfig, progress_ratio: float, expected_range: tuple[float, float]):
    client = ContreeSync(config=replace(config, token="test-token"))

    results = [client._get_interval(progress_ratio) for _ in range(200)]

    min_result = min(results)
    max_result = max(results)
    mean_result = sum(results) / len(results)

    assert expected_range[0] <= mean_result <= expected_range[1], f"Mean {mean_result:.2f} not in {expected_range}"
    assert min_result >= config.operation_poll_secs_min
    assert max_result <= config.operation_poll_secs_max
