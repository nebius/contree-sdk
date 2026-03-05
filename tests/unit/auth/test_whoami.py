from pytest_httpx import HTTPXMock

from contree_sdk import Contree, ContreeSync
from tests.e2e.sdk.test_auth import test_whoami as _test_whoami
from tests.e2e.sdk.test_auth import test_whoami_sync as _test_whoami_sync


async def test_whoami(fake_contree: Contree, token_uuid: str, api_fake_whoami: HTTPXMock):
    await _test_whoami(fake_contree)


def test_whoami_sync(fake_contree_s: ContreeSync, token_uuid: str, api_fake_whoami: HTTPXMock):
    _test_whoami_sync(fake_contree_s)
