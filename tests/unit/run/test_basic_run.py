from typing import Any

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


def instance_request_kwargs(api: Any) -> list[dict]:
    return [call.kwargs for call in api.calls_for("spawn_instance")]


async def test_basic_run(fake_image, api_fake_run):
    await _test_basic_run(fake_image)


async def test_run_flushes_caller_supplied_writer(fake_image, tmp_path, api_fake_run):
    out_path = tmp_path / "out.log"
    with out_path.open("wb") as file:
        await fake_image.run(shell="true", stdout=file)

        assert out_path.read_bytes() == b"my input\nthis is stdout\n"


async def test_run_result_exposes_cost(fake_image, api_fake_run):
    # `contree_client.models.EventDataExit.resources` (`EventResources`) has no
    # cost figure at all -- the old API's untyped exit-event `resources` dict
    # happened to carry one, the new typed model doesn't, so `cost` is always
    # None now.
    result = await fake_image.run(shell="true")

    assert result.result.cost is None


async def test_run_clears_source_tag(fake_image, result_image_uuid, api_fake_run):
    assert fake_image.tag is not None

    result = await fake_image.run(shell="true")

    assert result.uuid == result_image_uuid
    assert result.tag is None


async def test_basic_run_deferred(fake_image, api_fake_run_deferred):
    await _test_basic_run(fake_image)


def test_basic_run_s(fake_image_s, api_fake_run):
    _test_basic_run_s(fake_image_s)


def test_run_with_files_s(fake_image_s, test_txt_path, api_fake_run_with_files):
    _test_run_with_files_s(fake_image_s, test_txt_path)


async def test_run_preserve_env(fake_image, api_fake_run_preserve_env):
    await _test_run_preserve_env(fake_image)

    first_call, second_call = instance_request_kwargs(fake_image.client.api)
    assert first_call["env"] == {"SDK_PRESERVE_ENV": "ok"}
    assert first_call["preserve_env"] is True
    assert first_call["disposable"] is False
    assert second_call["preserve_env"] is False


def test_run_preserve_env_s(fake_image_s, api_fake_run_preserve_env):
    _test_run_preserve_env_s(fake_image_s)

    first_call, second_call = instance_request_kwargs(api_fake_run_preserve_env)
    assert first_call["env"] == {"SDK_PRESERVE_ENV_SYNC": "ok"}
    assert first_call["preserve_env"] is True
    assert first_call["disposable"] is False
    assert second_call["preserve_env"] is False


async def test_run_without_preserve_env_does_not_persist_env(fake_image, api_fake_run_without_preserve_env):
    await _test_run_without_preserve_env_does_not_persist_env(fake_image)

    first_call, second_call = instance_request_kwargs(fake_image.client.api)
    assert first_call["env"] == {"SDK_GHOST_ENV": "missing"}
    assert first_call["preserve_env"] is False
    assert first_call["disposable"] is False
    assert second_call["preserve_env"] is False


def test_run_without_preserve_env_does_not_persist_env_s(fake_image_s, api_fake_run_without_preserve_env):
    _test_run_without_preserve_env_does_not_persist_env_s(fake_image_s)

    first_call, second_call = instance_request_kwargs(api_fake_run_without_preserve_env)
    assert first_call["env"] == {"SDK_GHOST_ENV_SYNC": "missing"}
    assert first_call["preserve_env"] is False
    assert first_call["disposable"] is False
    assert second_call["preserve_env"] is False


async def test_run_with_file_spec_path(fake_image, test_txt_path, api_fake_run_with_files):
    await _test_run_with_file_spec_path(fake_image, test_txt_path)

    [call] = instance_request_kwargs(fake_image.client.api)
    assert set(call["files"]) == {"/data.txt"}


def test_run_with_file_spec_path_s(fake_image_s, test_txt_path, api_fake_run_with_files):
    _test_run_with_file_spec_path_s(fake_image_s, test_txt_path)

    [call] = instance_request_kwargs(api_fake_run_with_files)
    assert set(call["files"]) == {"/data.txt"}


def test_run_io_input_s(fake_image_s, api_fake_run):
    _test_run_io_input_s(fake_image_s)


def test_run_io_output_s(fake_image_s, api_fake_run):
    _test_run_io_output_s(fake_image_s)


def test_run_file_io_s(fake_image_s, tmp_file, test_txt_path, api_fake_run_with_files):
    _test_run_file_io_s(fake_image_s, tmp_file, test_txt_path)


async def test_run_truncated_output(fake_image, api_fake_run_truncated):
    await _test_run_truncated_output(fake_image)


async def test_preconfigured_run(fake_image, api_fake_thread_pool):
    await _test_preconfigured_run(fake_image)


async def test_apply_files(fake_image, test_txt_path, api_fake_apply_files):
    await _test_apply_files(fake_image, test_txt_path)


def test_apply_files_s(fake_image_s, test_txt_path, api_fake_apply_files):
    _test_apply_files_s(fake_image_s, test_txt_path)
