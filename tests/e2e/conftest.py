from collections.abc import AsyncIterator, Iterator
from os import getenv

import pytest
from contree_client import asyncio as contree_asyncio
from contree_client import sync as contree_sync
from contree_client.base import ContreeAsyncClient, ContreeSyncClient

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
async def async_client(_contree_token: str, _contree_project_id: str) -> AsyncIterator[ContreeAsyncClient]:
    async with contree_asyncio.ContreeAsyncClient(
        _contree_token, base_url=TOKEN_FACTORY_SANDBOXES_URL, project=_contree_project_id or None
    ) as api:
        yield api


@pytest.fixture
def sync_client(_contree_token: str, _contree_project_id: str) -> Iterator[ContreeSyncClient]:
    with contree_sync.ContreeClient(
        _contree_token, base_url=TOKEN_FACTORY_SANDBOXES_URL, project=_contree_project_id or None
    ) as api:
        yield api


@pytest.fixture
def contree(async_client: ContreeAsyncClient) -> Contree:
    return Contree(async_client)


@pytest.fixture
def contree_s(sync_client: ContreeSyncClient) -> ContreeSync:
    return ContreeSync(sync_client)
