from os import getenv

import pytest

from contree_sdk import Contree
from contree_sdk._internals.utils.config import ContreeEndpoint
from contree_sdk.config import ContreeConfig


LOW_LIMITS_TOKEN_ENV_VAR = "CONTREE_SDK_TOKEN_E2E_TESTS_LOW_LIMITS"  # noqa: S105


@pytest.fixture
def low_limits_contree() -> Contree:
    token = getenv(LOW_LIMITS_TOKEN_ENV_VAR)
    if not token:
        pytest.skip(f"{LOW_LIMITS_TOKEN_ENV_VAR} not set")
    return Contree(config=ContreeConfig(token=token, base_url=ContreeEndpoint.PROD_NORTH))
