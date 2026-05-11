from os import getenv

import pytest

from contree_sdk import Contree, ContreeSync
from contree_sdk._internals.utils.config import ContreeEndpoint
from contree_sdk.auth import IAMAuth
from contree_sdk.config import ContreeConfig
from tests.utils.marker import create_directory_marker


pytest_collection_modifyitems, should_be_marked_e2e = create_directory_marker(pytest.mark.e2e)

CONTREE_TOKEN_TESTS_ENV_VAR = "CONTREE_SDK_TOKEN_E2E_TESTS"  # noqa: S105


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
def contree_config(_contree_project_id: str) -> ContreeConfig:
    return ContreeConfig(
        auth=IAMAuth(
            token=CONTREE_TOKEN_TESTS_ENV_VAR,
            base_url=ContreeEndpoint.TOKEN_FACTORY_SANDBOXES,
            project_id=_contree_project_id,
        )
    )


@pytest.fixture
def contree(contree_config: ContreeConfig) -> Contree:
    return Contree(config=contree_config)


@pytest.fixture
def contree_s(contree_config: ContreeConfig) -> ContreeSync:
    return ContreeSync(config=contree_config)
