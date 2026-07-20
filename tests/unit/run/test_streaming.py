from pytest_httpx import HTTPXMock

from tests.e2e.sdk.run.test_streaming import test_iterate_run_output as _test_iterate_run_output
from tests.e2e.sdk.run.test_streaming import test_iterate_run_output_s as _test_iterate_run_output_s
from tests.e2e.sdk.run.test_streaming import test_multiple_awaits_share_result as _test_multiple_awaits_share_result
from tests.e2e.sdk.run.test_streaming import test_start_then_await as _test_start_then_await


async def test_start_then_await(fake_image, api_fake_run: HTTPXMock):
    await _test_start_then_await(fake_image)


async def test_multiple_awaits_share_result(fake_image, api_fake_run: HTTPXMock):
    await _test_multiple_awaits_share_result(fake_image)


async def test_iterate_run_output(fake_image, api_fake_run: HTTPXMock):
    await _test_iterate_run_output(fake_image)


def test_iterate_run_output_s(fake_image_s, api_fake_run: HTTPXMock):
    _test_iterate_run_output_s(fake_image_s)
