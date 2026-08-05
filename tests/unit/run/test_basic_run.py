import json

from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture

from contree_sdk.sdk.exceptions import ContreeTransportError
from tests.e2e.sdk.run.test_basic_run import test_apply_files as _test_apply_files
from tests.e2e.sdk.run.test_basic_run import test_apply_files_s as _test_apply_files_s
from tests.e2e.sdk.run.test_basic_run import test_basic_run as _test_basic_run
from tests.e2e.sdk.run.test_basic_run import test_basic_run_s as _test_basic_run_s
from tests.e2e.sdk.run.test_basic_run import test_preconfigured_run as _test_preconfigured_run
from tests.e2e.sdk.run.test_basic_run import test_run_file_io_s as _test_run_file_io_s
from tests.e2e.sdk.run.test_basic_run import test_run_io_input_s as _test_run_io_input_s
from tests.e2e.sdk.run.test_basic_run import test_run_io_output_s as _test_run_io_output_s
from tests.e2e.sdk.run.test_basic_run import test_run_preserve_env as _test_run_preserve_env
from tests.e2e.sdk.run.test_basic_run import test_run_preserve_env_s as _test_run_preserve_env_s
from tests.e2e.sdk.run.test_basic_run import test_run_truncated_output as _test_run_truncated_output
from tests.e2e.sdk.run.test_basic_run import test_run_with_file_spec_path as _test_run_with_file_spec_path
from tests.e2e.sdk.run.test_basic_run import test_run_with_file_spec_path_s as _test_run_with_file_spec_path_s
from tests.e2e.sdk.run.test_basic_run import test_run_with_files_s as _test_run_with_files_s
from tests.e2e.sdk.run.test_basic_run import (
    test_run_without_preserve_env_does_not_persist_env as _test_run_without_preserve_env_does_not_persist_env,
)
from tests.e2e.sdk.run.test_basic_run import (
    test_run_without_preserve_env_does_not_persist_env_s as _test_run_without_preserve_env_does_not_persist_env_s,
)
from tests.unit.fixtures.operations import OPERATION_COST


def _instance_request_bodies(api_mock: HTTPXMock) -> list[dict]:
    return [
        json.loads(request.read().decode())
        for request in api_mock.get_requests()
        if request.method == "POST" and request.url.path.endswith("/instances")
    ]


async def test_basic_run(fake_image, api_fake_run: HTTPXMock):
    await _test_basic_run(fake_image)


async def test_run_flushes_caller_supplied_writer(fake_image, tmp_path, api_fake_run: HTTPXMock):
    out_path = tmp_path / "out.log"
    with out_path.open("wb") as file:
        await fake_image.run(shell="true", stdout=file)

        assert out_path.read_bytes() == b"my input\nthis is stdout\n"


async def test_run_result_exposes_cost(fake_image, operation_id: str, api_fake_run: HTTPXMock):
    result = await fake_image.run(shell="true")

    assert result.result.cost == OPERATION_COST
    status_requests = [
        request
        for request in api_fake_run.get_requests()
        if request.method == "GET" and request.url.path.endswith(f"/operations/{operation_id}")
    ]
    assert len(status_requests) == 1


async def test_run_succeeds_when_temporary_cost_request_fails(
    fake_image,
    api_fake_run: HTTPXMock,
    mocker: MockerFixture,
):
    mocker.patch.object(
        fake_image._client._api,
        "get_operation_status",
        side_effect=ContreeTransportError(error="unavailable"),
    )

    result = await fake_image.run(shell="true")

    assert result.result.cost is None


async def test_run_applies_request_output_limit_locally(fake_image, api_fake_run: HTTPXMock):
    result = await fake_image.run(shell="true", truncate_output_at=5)

    assert result.stdout == "my in"
    assert result.stderr == "this "
    assert result.result.truncated["stdout"].bytes_dropped == 19
    assert result.result.truncated["stderr"].bytes_dropped == 10
    [request_body] = _instance_request_bodies(api_fake_run)
    assert request_body["truncate_output_at"] == 5


async def test_run_clears_source_tag(fake_image, result_image_uuid, api_fake_run: HTTPXMock):
    assert fake_image.tag is not None

    result = await fake_image.run(shell="true")

    assert result.uuid == result_image_uuid
    assert result.tag is None


async def test_basic_run_deferred(fake_image, api_fake_run_deferred: HTTPXMock):
    await _test_basic_run(fake_image)


def test_basic_run_s(fake_image_s, api_fake_run: HTTPXMock):
    _test_basic_run_s(fake_image_s)


def test_run_with_files_s(fake_image_s, test_txt_path, api_fake_run_with_files: HTTPXMock):
    _test_run_with_files_s(fake_image_s, test_txt_path)


async def test_run_preserve_env(fake_image, api_fake_run_preserve_env: HTTPXMock):
    await _test_run_preserve_env(fake_image)

    first_request_body, second_request_body = _instance_request_bodies(api_fake_run_preserve_env)
    assert first_request_body["env"] == {"SDK_PRESERVE_ENV": "ok"}
    assert first_request_body["preserve_env"] is True
    assert first_request_body["disposable"] is False
    assert second_request_body["preserve_env"] is False


def test_run_preserve_env_s(fake_image_s, api_fake_run_preserve_env: HTTPXMock):
    _test_run_preserve_env_s(fake_image_s)

    first_request_body, second_request_body = _instance_request_bodies(api_fake_run_preserve_env)
    assert first_request_body["env"] == {"SDK_PRESERVE_ENV_SYNC": "ok"}
    assert first_request_body["preserve_env"] is True
    assert first_request_body["disposable"] is False
    assert second_request_body["preserve_env"] is False


async def test_run_without_preserve_env_does_not_persist_env(fake_image, api_fake_run_without_preserve_env: HTTPXMock):
    await _test_run_without_preserve_env_does_not_persist_env(fake_image)

    first_request_body, second_request_body = _instance_request_bodies(api_fake_run_without_preserve_env)
    assert first_request_body["env"] == {"SDK_GHOST_ENV": "missing"}
    assert first_request_body["preserve_env"] is False
    assert first_request_body["disposable"] is False
    assert second_request_body["preserve_env"] is False


def test_run_without_preserve_env_does_not_persist_env_s(fake_image_s, api_fake_run_without_preserve_env: HTTPXMock):
    _test_run_without_preserve_env_does_not_persist_env_s(fake_image_s)

    first_request_body, second_request_body = _instance_request_bodies(api_fake_run_without_preserve_env)
    assert first_request_body["env"] == {"SDK_GHOST_ENV_SYNC": "missing"}
    assert first_request_body["preserve_env"] is False
    assert first_request_body["disposable"] is False
    assert second_request_body["preserve_env"] is False


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
