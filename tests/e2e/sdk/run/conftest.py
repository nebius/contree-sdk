from collections.abc import AsyncIterator
from os import getenv

import pytest
from contree_client.httpx import ContreeAsyncClient

from contree_sdk import Contree


LOW_LIMITS_TOKEN_ENV_VAR = "CONTREE_SDK_TOKEN_E2E_TESTS_LOW_LIMITS"
PROD_NORTH_URL = "https://eu-north.nebius.computer"


@pytest.fixture
async def low_limits_contree() -> AsyncIterator[Contree]:
    token = getenv(LOW_LIMITS_TOKEN_ENV_VAR)
    if not token:
        pytest.skip(f"{LOW_LIMITS_TOKEN_ENV_VAR} not set")
    async with ContreeAsyncClient(token, base_url=PROD_NORTH_URL) as api:
        yield Contree(api)
