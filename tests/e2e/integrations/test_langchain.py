from os import getenv

import pytest


try:
    from langchain_tests.integration_tests import SandboxIntegrationTests
except ImportError:
    pytest.skip(
        "langchain-tests/deepagents integration dependencies are not available (requires Python >= 3.11)",
        allow_module_level=True,
    )

from contree_client.sync import ContreeClient

from contree_sdk import ContreeSync
from contree_sdk.langchain.sandbox import ContreeSandbox


class TestConTreeSandbox(SandboxIntegrationTests):
    @pytest.fixture(scope="class")
    async def sandbox(self):
        token = getenv("CONTREE_SDK_TOKEN_E2E_TESTS") or ""
        api = ContreeClient(token)
        client = ContreeSync(api)
        session = client.images.oci("python:3.12").session()
        return ContreeSandbox(session)
