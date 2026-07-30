import pytest


try:
    from langchain_tests.integration_tests import SandboxIntegrationTests
except ImportError:
    pytest.skip(
        "langchain-tests/deepagents integration dependencies are not available (requires Python >= 3.11)",
        allow_module_level=True,
    )

from contree_sdk import ContreeSync
from contree_sdk.auth import IAMAuth
from contree_sdk.config import ContreeConfig
from contree_sdk.langchain.sandbox import ContreeSandbox


class TestConTreeSandbox(SandboxIntegrationTests):
    @pytest.fixture(scope="class")
    async def sandbox(self):
        config = ContreeConfig(
            auth=IAMAuth(
                token="CONTREE_SDK_TOKEN_E2E_TESTS",
            )
        )
        client = ContreeSync(config=config)
        session = client.images.oci("python:3.12").session()
        return ContreeSandbox(session=session)
