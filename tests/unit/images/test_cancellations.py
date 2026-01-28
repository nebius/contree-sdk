from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture

from contree_sdk import Contree, ContreeSync
from tests.e2e.sdk.test_cancellations import test_cancel_import as _test_cancel_import
from tests.e2e.sdk.test_cancellations import test_cancel_import_s as _test_cancel_import_s


async def test_cancel_import(fake_contree: Contree, api_fake_import_cancel: HTTPXMock, mocker: MockerFixture):
    await _test_cancel_import(fake_contree, mocker)


async def test_cancel_import_s(
    fake_contree: Contree, fake_contree_s: ContreeSync, api_fake_import_slow: HTTPXMock, mocker: MockerFixture
):
    await _test_cancel_import_s(fake_contree, fake_contree_s, mocker)
