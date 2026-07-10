from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture

from contree_sdk import Contree
from contree_sdk.sdk.objects.image import ContreeImage
from tests.e2e.sdk.test_operations import test_stream_operation_events as _test_stream_operation_events


async def test_stream_operation_events(
    fake_contree: Contree, fake_image: ContreeImage, api_fake_streamed_run: HTTPXMock, mocker: MockerFixture
):
    await _test_stream_operation_events(fake_contree, fake_image, mocker)
