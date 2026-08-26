from collections.abc import AsyncIterator, Iterator
from os import getenv

import pytest
from contree_client.httpx import ContreeAsyncClient, ContreeClient

from contree_sdk import Contree, ContreeSync
from tests.utils.marker import create_directory_marker


pytest_collection_modifyitems, should_be_marked_e2e = create_directory_marker(pytest.mark.e2e)

CONTREE_TOKEN_TESTS_ENV_VAR = "CONTREE_SDK_TOKEN_E2E_TESTS"
TOKEN_FACTORY_SANDBOXES_URL = "https://api.tokenfactory.nebius.com/sandboxes/"


@pytest.fixture
def _contree_token() -> str:
    value = getenv(CONTREE_TOKEN_TESTS_ENV_VAR)
    if not value:
        raise RuntimeError(f"Environment variable {CONTREE_TOKEN_TESTS_ENV_VAR} is required for E2E tests")
    return value


_CONTREE_PROJECT_ID = getenv("NEBIUS_PROJECT_ID") or ""


@pytest.fixture
def _contree_project_id() -> str:
    return _CONTREE_PROJECT_ID


@pytest.fixture
async def contree(_contree_token: str, _contree_project_id: str) -> AsyncIterator[Contree]:
    async with ContreeAsyncClient(
        _contree_token, base_url=TOKEN_FACTORY_SANDBOXES_URL, project=_contree_project_id or None
    ) as api:
        yield Contree(api)


@pytest.fixture
def contree_s(_contree_token: str, _contree_project_id: str) -> Iterator[ContreeSync]:
    with ContreeClient(
        _contree_token, base_url=TOKEN_FACTORY_SANDBOXES_URL, project=_contree_project_id or None
    ) as api:
        yield ContreeSync(api)
