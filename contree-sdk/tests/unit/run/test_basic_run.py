from pytest_httpx import HTTPXMock

from tests.e2e.sdk.run.test_basic_run import test_basic_run as _test_basic_run
from tests.e2e.sdk.run.test_basic_run import test_basic_run_s as _test_basic_run_s
from tests.e2e.sdk.run.test_basic_run import test_run_file_io_s as _test_run_file_io_s
from tests.e2e.sdk.run.test_basic_run import test_run_io_input_s as _test_run_io_input_s
from tests.e2e.sdk.run.test_basic_run import test_run_io_output_s as _test_run_io_output_s
from tests.e2e.sdk.run.test_basic_run import test_run_with_files_s as _test_run_with_files_s


async def test_basic_run(fake_image, api_fake_run: HTTPXMock):
    await _test_basic_run(fake_image)


def test_basic_run_s(fake_image_s, api_fake_run: HTTPXMock):
    _test_basic_run_s(fake_image_s)


def test_run_with_files_s(fake_image_s, test_txt_path, api_fake_run_with_files: HTTPXMock):
    _test_run_with_files_s(fake_image_s, test_txt_path)


def test_run_io_input_s(fake_image_s, api_fake_run: HTTPXMock):
    _test_run_io_input_s(fake_image_s)


def test_run_io_output_s(fake_image_s, api_fake_run: HTTPXMock):
    _test_run_io_output_s(fake_image_s)


def test_run_file_io_s(fake_image_s, test_txt_path, api_fake_run_with_files: HTTPXMock):
    _test_run_file_io_s(fake_image_s, test_txt_path)
