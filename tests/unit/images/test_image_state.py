from uuid import UUID, uuid4

import pytest
from contree_client.models import InstanceSpawnResponse

from contree_sdk.sdk.exceptions import ContreeImageStateError
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.sdk.objects.image_like.state import ImageState
from tests.unit.fixtures.operations import queue_run
from tests.unit.fixtures.runs import RUN_STDERR, RUN_STDOUT


def test_pulled_image_has_no_result(fake_image: ContreeImage):
    assert fake_image.state == ImageState.PULLED
    with pytest.raises(ContreeImageStateError):
        _ = fake_image.result


def test_run_prepares_a_copy(fake_image: ContreeImage):
    prepared = fake_image.run(shell="true")

    assert prepared.state == ImageState.PREPARED
    assert fake_image.state == ImageState.PULLED


async def test_await_unprepared_raises(fake_image: ContreeImage):
    with pytest.raises(ContreeImageStateError):
        await fake_image


async def test_executing_image_cannot_be_reconfigured(fake_image: ContreeImage, result_image_uuid: UUID):
    queue_run(fake_image.client.api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    started = await fake_image.run(shell="true").start()

    assert started.state == ImageState.EXECUTING
    with pytest.raises(ContreeImageStateError):
        started.run(shell="again")


async def test_succeeded_image_can_run_again(fake_image: ContreeImage, result_image_uuid: UUID):
    queue_run(fake_image.client.api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    result = await fake_image.run(shell="true")

    assert result.state == ImageState.SUCCEEDED
    assert result.run(shell="again").state == ImageState.PREPARED


async def test_transport_failure_transitions_to_failed(fake_image: ContreeImage):
    # Not a ContreeError of either hierarchy -- the state machine must still notice.
    fake_image.client.api.mock("spawn_instance", InstanceSpawnResponse(uuid=str(uuid4())))
    fake_image.client.api.mock("follow_operation_events", error=ConnectionError("transport blew up"))

    executing = await fake_image.run(shell="true").start()
    assert executing.state == ImageState.EXECUTING

    with pytest.raises(ConnectionError):
        await executing.wait()

    assert executing.state == ImageState.FAILED


def test_transport_failure_transitions_to_failed_s(fake_image_s: ContreeImageSync):
    fake_image_s.client.api.mock("spawn_instance", InstanceSpawnResponse(uuid=str(uuid4())))
    fake_image_s.client.api.mock("follow_operation_events", error=ConnectionError("transport blew up"))

    executing = fake_image_s.run(shell="true").start()
    assert executing.state == ImageState.EXECUTING

    with pytest.raises(ConnectionError):
        executing.wait()

    assert executing.state == ImageState.FAILED
