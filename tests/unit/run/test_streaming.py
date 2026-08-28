from uuid import UUID

from tests.e2e.sdk.run.test_streaming import test_iterate_run_output as _test_iterate_run_output
from tests.e2e.sdk.run.test_streaming import test_iterate_run_output_s as _test_iterate_run_output_s
from tests.e2e.sdk.run.test_streaming import test_multiple_awaits_share_result as _test_multiple_awaits_share_result
from tests.e2e.sdk.run.test_streaming import test_start_then_await as _test_start_then_await
from tests.unit.fixtures.operations import queue_run
from tests.unit.fixtures.runs import RUN_STDERR, RUN_STDOUT


async def test_start_then_await(fake_image, result_image_uuid: UUID):
    queue_run(fake_image.client.api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    await _test_start_then_await(fake_image)


async def test_multiple_awaits_share_result(fake_image, result_image_uuid: UUID):
    queue_run(fake_image.client.api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    await _test_multiple_awaits_share_result(fake_image)


async def test_iterate_run_output(fake_image, result_image_uuid: UUID):
    queue_run(fake_image.client.api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    await _test_iterate_run_output(fake_image)


def test_iterate_run_output_s(fake_image_s, result_image_uuid: UUID):
    queue_run(fake_image_s.client.api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    _test_iterate_run_output_s(fake_image_s)
