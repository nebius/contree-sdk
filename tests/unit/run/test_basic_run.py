import json

from pytest_httpx import HTTPXMock

from tests.e2e.sdk.run.test_basic_run import test_apply_files as _test_apply_files
from tests.e2e.sdk.run.test_basic_run import test_apply_files_s as _test_apply_files_s
from tests.e2e.sdk.run.test_basic_run import test_basic_run as _test_basic_run
from tests.e2e.sdk.run.test_basic_run import test_basic_run_s as _test_basic_run_s
from tests.e2e.sdk.run.test_basic_run import test_preconfigured_run as _test_preconfigured_run
from tests.e2e.sdk.run.test_basic_run import test_run_file_io_s as _test_run_file_io_s
from tests.e2e.sdk.run.test_basic_run import test_run_io_input_s as _test_run_io_input_s
from tests.e2e.sdk.run.test_basic_run import test_run_io_output_s as _test_run_io_output_s
from tests.e2e.sdk.run.test_basic_run import test_run_truncated_output as _test_run_truncated_output
from tests.e2e.sdk.run.test_basic_run import test_run_with_file_spec_path as _test_run_with_file_spec_path
from tests.e2e.sdk.run.test_basic_run import test_run_with_file_spec_path_s as _test_run_with_file_spec_path_s
from tests.e2e.sdk.run.test_basic_run import test_run_with_files_s as _test_run_with_files_s


def _instance_request_bodies(api_mock: HTTPXMock) -> list[dict]:
    return [
        json.loads(request.read().decode())
        for request in api_mock.get_requests()
        if request.method == "POST" and request.url.path.endswith("/instances")
    ]


async def test_basic_run_sends_default_preserve_env(fake_image, api_fake_run: HTTPXMock):
    await fake_image.run(shell="true")

    [request_body] = _instance_request_bodies(api_fake_run)
    assert request_body["preserve_env"] is False


async def test_basic_run(fake_image, api_fake_run: HTTPXMock):
    await _test_basic_run(fake_image)


async def test_basic_run_deferred(fake_image, api_fake_run_deferred: HTTPXMock):
    await _test_basic_run(fake_image)


def test_basic_run_s(fake_image_s, api_fake_run: HTTPXMock):
    _test_basic_run_s(fake_image_s)


def test_run_with_files_s(fake_image_s, test_txt_path, api_fake_run_with_files: HTTPXMock):
    _test_run_with_files_s(fake_image_s, test_txt_path)


def test_run_sends_preserve_env(fake_image_s, api_fake_run: HTTPXMock):
    fake_image_s.run(
        shell="true",
        env={"SDK_PRESERVE_ENV": "ok"},
        preserve_env=True,
        disposable=False,
    ).wait()

    [request_body] = _instance_request_bodies(api_fake_run)
    assert request_body["env"] == {"SDK_PRESERVE_ENV": "ok"}
    assert request_body["preserve_env"] is True
    assert request_body["disposable"] is False


async def test_run_with_file_spec_path(fake_image, test_txt_path, api_fake_run_with_files: HTTPXMock):
    await _test_run_with_file_spec_path(fake_image, test_txt_path)

    [request_body] = _instance_request_bodies(api_fake_run_with_files)
    assert set(request_body["files"]) == {"/data.txt"}


def test_run_with_file_spec_path_s(fake_image_s, test_txt_path, api_fake_run_with_files: HTTPXMock):
    _test_run_with_file_spec_path_s(fake_image_s, test_txt_path)

    [request_body] = _instance_request_bodies(api_fake_run_with_files)
    assert set(request_body["files"]) == {"/data.txt"}


def test_run_io_input_s(fake_image_s, api_fake_run: HTTPXMock):
    _test_run_io_input_s(fake_image_s)


def test_run_io_output_s(fake_image_s, api_fake_run: HTTPXMock):
    _test_run_io_output_s(fake_image_s)


def test_run_file_io_s(fake_image_s, tmp_file, test_txt_path, api_fake_run_with_files: HTTPXMock):
    _test_run_file_io_s(fake_image_s, tmp_file, test_txt_path)


async def test_run_truncated_output(fake_image, api_fake_run_truncated: HTTPXMock):
    await _test_run_truncated_output(fake_image)


async def test_preconfigured_run(fake_image, api_fake_thread_pool: HTTPXMock):
    await _test_preconfigured_run(fake_image)


async def test_apply_files(fake_image, test_txt_path, api_fake_apply_files: HTTPXMock):
    await _test_apply_files(fake_image, test_txt_path)


def test_apply_files_s(fake_image_s, test_txt_path, api_fake_apply_files: HTTPXMock):
    _test_apply_files_s(fake_image_s, test_txt_path)
