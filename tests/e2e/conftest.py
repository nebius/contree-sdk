from os import getenv

import pytest

from contree_sdk import Contree, ContreeSync
from contree_sdk._internals.utils.config import ContreeEndpoint
from contree_sdk.config import ContreeConfig
from tests.utils.marker import create_directory_marker


pytest_collection_modifyitems, should_be_marked_e2e = create_directory_marker(pytest.mark.e2e)


@pytest.fixture
def _contree_token() -> str:
    value = getenv("CONTREE_SDK_TOKEN_E2E_TESTS")
    if not value:
        raise RuntimeError("Environment variable CONTREE_SDK_TOKEN_E2E_TESTS is required for E2E tests")
    return value


@pytest.fixture
def contree_config(_contree_token: str) -> ContreeConfig:
    return ContreeConfig(
        token=_contree_token,
        base_url=ContreeEndpoint.PROD_NORTH,
    )


@pytest.fixture
def contree(contree_config: ContreeConfig) -> Contree:
    return Contree(config=contree_config)


@pytest.fixture
def contree_s(contree_config: ContreeConfig) -> ContreeSync:
    return ContreeSync(config=contree_config)
