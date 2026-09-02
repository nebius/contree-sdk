from typing import Any
from uuid import UUID

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
from tests.unit.fixtures.files import queue_upload
from tests.unit.fixtures.operations import OPERATION_COST, queue_run
from tests.unit.fixtures.runs import FILE_SHA256, FILE_UUID, RUN_STDERR, RUN_STDOUT


def instance_request_kwargs(api: Any) -> list[dict]:
    return [call.kwargs for call in api.calls_for("spawn_instance")]


async def test_basic_run(fake_image, result_image_uuid: UUID):
    queue_run(fake_image.client.api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    await _test_basic_run(fake_image)


async def test_run_flushes_caller_supplied_writer(fake_image, tmp_path, result_image_uuid: UUID):
    queue_run(fake_image.client.api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    out_path = tmp_path / "out.log"
    with out_path.open("wb") as file:
        await fake_image.run(shell="true", stdout=file)

        assert out_path.read_bytes() == b"my input\nthis is stdout\n"


async def test_run_result_exposes_cost(fake_image, result_image_uuid: UUID):
    # Cost comes from get_operation_status, not the exit event.
    queue_run(
        fake_image.client.api,
        stdout=RUN_STDOUT,
        stderr=RUN_STDERR,
        result_image_uuid=str(result_image_uuid),
        cost=OPERATION_COST,
    )
    result = await fake_image.run(shell="true")

    assert result.result.cost == OPERATION_COST


async def test_run_caps_client_side_output_at_truncate_output_at(fake_image, result_image_uuid: UUID):
    # The waiter enforces truncate_output_at client-side too, not just the server.
    queue_run(fake_image.client.api, stdout="hello world", stderr="", result_image_uuid=str(result_image_uuid))
    result = await fake_image.run(shell="true", truncate_output_at=4, stdout=bytes)

    assert result.result.stdout == b"hell"


async def test_run_result_cost_is_none_when_unavailable(fake_image, result_image_uuid: UUID):
    queue_run(fake_image.client.api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    result = await fake_image.run(shell="true")

    assert result.result.cost is None


async def test_run_clears_source_tag(fake_image, result_image_uuid: UUID):
    queue_run(fake_image.client.api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    assert fake_image.tag is not None

    result = await fake_image.run(shell="true")

    assert result.uuid == result_image_uuid
    assert result.tag is None


async def test_basic_run_deferred(fake_image, result_image_uuid: UUID):
    # `not_found_first` (a transient 404 before the events stream comes up) is now
    # contree_client's own reconnect concern (`follow_operation_events`), nothing
    # left for contree_sdk to special-case -- this is the same canned run as
    # a plain `test_basic_run`.
    queue_run(fake_image.client.api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    await _test_basic_run(fake_image)


def test_basic_run_s(fake_image_s, result_image_uuid: UUID):
    queue_run(fake_image_s.client.api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    _test_basic_run_s(fake_image_s)


def test_run_with_files_s(fake_image_s, test_txt_path, result_image_uuid: UUID):
    queue_upload(fake_image_s.client.api, FILE_UUID, FILE_SHA256)
    queue_run(fake_image_s.client.api, stdout="second line\nlast line\n", result_image_uuid=str(result_image_uuid))
    _test_run_with_files_s(fake_image_s, test_txt_path)


async def test_run_preserve_env(fake_image, result_image_uuid: UUID):
    # the second `.run()` chains off the first run's *result* image, so that
    # result needs a live `uuid` too.
    queue_run(fake_image.client.api, stdout="", result_image_uuid=str(result_image_uuid))
    queue_run(fake_image.client.api, stdout="ok\n", result_image_uuid=str(result_image_uuid))
    await _test_run_preserve_env(fake_image)

    first_call, second_call = instance_request_kwargs(fake_image.client.api)
    assert first_call["env"] == {"SDK_PRESERVE_ENV": "ok"}
    assert first_call["preserve_env"] is True
    assert first_call["disposable"] is False
    assert second_call["preserve_env"] is False


def test_run_preserve_env_s(fake_image_s, result_image_uuid: UUID):
    queue_run(fake_image_s.client.api, stdout="", result_image_uuid=str(result_image_uuid))
    queue_run(fake_image_s.client.api, stdout="ok\n", result_image_uuid=str(result_image_uuid))
    _test_run_preserve_env_s(fake_image_s)

    first_call, second_call = instance_request_kwargs(fake_image_s.client.api)
    assert first_call["env"] == {"SDK_PRESERVE_ENV_SYNC": "ok"}
    assert first_call["preserve_env"] is True
    assert first_call["disposable"] is False
    assert second_call["preserve_env"] is False


async def test_run_without_preserve_env_does_not_persist_env(fake_image, result_image_uuid: UUID):
    queue_run(fake_image.client.api, stdout="", result_image_uuid=str(result_image_uuid))
    queue_run(fake_image.client.api, stdout="", result_image_uuid=str(result_image_uuid))
    await _test_run_without_preserve_env_does_not_persist_env(fake_image)

    first_call, second_call = instance_request_kwargs(fake_image.client.api)
    assert first_call["env"] == {"SDK_GHOST_ENV": "missing"}
    assert first_call["preserve_env"] is False
    assert first_call["disposable"] is False
    assert second_call["preserve_env"] is False


def test_run_without_preserve_env_does_not_persist_env_s(fake_image_s, result_image_uuid: UUID):
    queue_run(fake_image_s.client.api, stdout="", result_image_uuid=str(result_image_uuid))
    queue_run(fake_image_s.client.api, stdout="", result_image_uuid=str(result_image_uuid))
    _test_run_without_preserve_env_does_not_persist_env_s(fake_image_s)

    first_call, second_call = instance_request_kwargs(fake_image_s.client.api)
    assert first_call["env"] == {"SDK_GHOST_ENV_SYNC": "missing"}
    assert first_call["preserve_env"] is False
    assert first_call["disposable"] is False
    assert second_call["preserve_env"] is False


async def test_run_with_file_spec_path(fake_image, test_txt_path, result_image_uuid: UUID):
    queue_upload(fake_image.client.api, FILE_UUID, FILE_SHA256)
    queue_run(fake_image.client.api, stdout="second line\nlast line\n", result_image_uuid=str(result_image_uuid))
    await _test_run_with_file_spec_path(fake_image, test_txt_path)

    [call] = instance_request_kwargs(fake_image.client.api)
    assert set(call["files"]) == {"/data.txt"}


def test_run_with_file_spec_path_s(fake_image_s, test_txt_path, result_image_uuid: UUID):
    queue_upload(fake_image_s.client.api, FILE_UUID, FILE_SHA256)
    queue_run(fake_image_s.client.api, stdout="second line\nlast line\n", result_image_uuid=str(result_image_uuid))
    _test_run_with_file_spec_path_s(fake_image_s, test_txt_path)

    [call] = instance_request_kwargs(fake_image_s.client.api)
    assert set(call["files"]) == {"/data.txt"}


def test_run_io_input_s(fake_image_s, result_image_uuid: UUID):
    queue_run(fake_image_s.client.api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    _test_run_io_input_s(fake_image_s)


def test_run_io_output_s(fake_image_s, result_image_uuid: UUID):
    queue_run(fake_image_s.client.api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    _test_run_io_output_s(fake_image_s)


def test_run_file_io_s(fake_image_s, tmp_file, test_txt_path, result_image_uuid: UUID):
    queue_upload(fake_image_s.client.api, FILE_UUID, FILE_SHA256)
    queue_run(fake_image_s.client.api, stdout="second line\nlast line\n", result_image_uuid=str(result_image_uuid))
    _test_run_file_io_s(fake_image_s, tmp_file, test_txt_path)


async def test_run_truncated_output(fake_image, result_image_uuid: UUID):
    queue_run(fake_image.client.api, stdout="a" * 50, result_image_uuid=str(result_image_uuid))
    await _test_run_truncated_output(fake_image)


async def test_preconfigured_run(fake_image):
    for i in range(10):
        queue_run(fake_image.client.api, stdout=f"{10000 + i * 1000}\n")
    await _test_preconfigured_run(fake_image)


async def test_apply_files(fake_image, test_txt_path, result_image_uuid: UUID):
    queue_upload(fake_image.client.api, FILE_UUID, FILE_SHA256)
    queue_run(fake_image.client.api, stdout="", result_image_uuid=str(result_image_uuid))
    queue_run(fake_image.client.api, stdout="second line\nlast line\n", result_image_uuid=str(result_image_uuid))
    await _test_apply_files(fake_image, test_txt_path)


def test_apply_files_s(fake_image_s, test_txt_path, result_image_uuid: UUID):
    queue_upload(fake_image_s.client.api, FILE_UUID, FILE_SHA256)
    queue_run(fake_image_s.client.api, stdout="", result_image_uuid=str(result_image_uuid))
    queue_run(fake_image_s.client.api, stdout="second line\nlast line\n", result_image_uuid=str(result_image_uuid))
    _test_apply_files_s(fake_image_s, test_txt_path)
