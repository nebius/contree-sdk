import pytest
from langchain_tests.integration_tests import SandboxIntegrationTests

from contree_sdk import ContreeSync
from contree_sdk.langchain.sandbox import ContreeSandbox


class TestConTreeSandbox(SandboxIntegrationTests):
    @pytest.fixture(scope="class")
    async def sandbox(self):
        client = ContreeSync()
        session = client.images.oci("python:3.12").session()
        return ContreeSandbox(session=session)
