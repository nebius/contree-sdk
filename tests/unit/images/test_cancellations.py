from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture

from contree_sdk import Contree, ContreeSync
from contree_sdk.sdk.objects.image import ContreeImage
from tests.e2e.sdk.test_cancellations import test_cancel_import as _test_cancel_import
from tests.e2e.sdk.test_cancellations import test_cancel_import_s as _test_cancel_import_s
from tests.e2e.sdk.test_cancellations import (
    test_timed_out_wait_cancels_operation as _test_timed_out_wait_cancels_operation,
)


async def test_cancel_import(fake_contree: Contree, api_fake_import_cancel: HTTPXMock, mocker: MockerFixture):
    await _test_cancel_import(fake_contree, mocker)


async def test_cancel_import_s(fake_contree_s: ContreeSync, api_fake_import_slow: HTTPXMock, mocker: MockerFixture):
    await _test_cancel_import_s(fake_contree_s, mocker)


async def test_timed_out_wait_cancels_operation(
    fake_contree: Contree, fake_image: ContreeImage, api_fake_slow_run: HTTPXMock, mocker: MockerFixture
):
    await _test_timed_out_wait_cancels_operation(fake_contree, fake_image, mocker)
