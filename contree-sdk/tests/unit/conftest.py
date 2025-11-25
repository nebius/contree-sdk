import pytest

from contree_sdk import Contree, ContreeSync
from contree_sdk.config import ContreeConfig


@pytest.fixture()
def fake_contree_config() -> ContreeConfig:
    return ContreeConfig(
        token="fake-token",
        base_url="https://fake.contree.endpoint",
    )


@pytest.fixture()
def fake_contree(fake_contree_config: ContreeConfig) -> Contree:
    return Contree(config=fake_contree_config)


@pytest.fixture()
def fake_contree_s(fake_contree_config: ContreeConfig) -> ContreeSync:
    return ContreeSync(config=fake_contree_config)
