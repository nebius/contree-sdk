from io import BytesIO
from uuid import UUID

import pytest
from contree_client.models import OperationResponse, OperationStatus

from contree_sdk.sdk.exceptions import CancelledOperationError, FailedOperationError, OperationTimedOutError
from contree_sdk.sdk.objects.image_like.waiter_async import OperationWaiter as AsyncOperationWaiter
from contree_sdk.sdk.objects.image_like.waiter_common import MAIN_SPID
from contree_sdk.sdk.objects.image_like.waiter_sync import OperationWaiter as SyncOperationWaiter
from tests.unit.fixtures.operations import run_events


def queue_events_and_status(
    api, operation_id: str, *, status: OperationStatus = OperationStatus.SUCCESS, result_image_uuid=None, **kwargs
) -> None:
    api.mock("follow_operation_events", run_events(status=status, result_image_uuid=result_image_uuid, **kwargs))
    api.mock(
        "get_operation_status",
        OperationResponse(
            uuid=operation_id, status=status, result_image_uuid=result_image_uuid, error=kwargs.get("error")
        ),
    )


async def test_wait_for_result_success(fake_api, operation_id: str, result_image_uuid: UUID):
    queue_events_and_status(
        fake_api, operation_id, stdout="hi\n", stderr="oops\n", result_image_uuid=str(result_image_uuid)
    )

    waiter = AsyncOperationWaiter(fake_api, operation_id)
    response, exit_event = await waiter.wait_for_result()

    assert response.status == OperationStatus.SUCCESS
    assert response.result_image_uuid == str(result_image_uuid)
    assert exit_event is not None
    assert exit_event.code == 0

    view = waiter.process_view()
    assert view.outputs["stdout"] == b"hi\n"
    assert view.outputs["stderr"] == b"oops\n"


def test_wait_for_result_success_sync(fake_api_s, operation_id: str, result_image_uuid: UUID):
    queue_events_and_status(
        fake_api_s, operation_id, stdout="hi\n", stderr="oops\n", result_image_uuid=str(result_image_uuid)
    )

    waiter = SyncOperationWaiter(fake_api_s, operation_id)
    response, exit_event = waiter.wait_for_result()

    assert response.status == OperationStatus.SUCCESS
    assert exit_event is not None
    assert exit_event.code == 0

    view = waiter.process_view()
    assert view.outputs["stdout"] == b"hi\n"
    assert view.outputs["stderr"] == b"oops\n"


async def test_wait_for_result_failed(fake_api, operation_id: str):
    queue_events_and_status(fake_api, operation_id, status=OperationStatus.FAILED, error="boom")

    waiter = AsyncOperationWaiter(fake_api, operation_id)
    with pytest.raises(FailedOperationError):
        await waiter.wait_for_result()


def test_wait_for_result_failed_sync(fake_api_s, operation_id: str):
    queue_events_and_status(fake_api_s, operation_id, status=OperationStatus.FAILED, error="boom")

    waiter = SyncOperationWaiter(fake_api_s, operation_id)
    with pytest.raises(FailedOperationError):
        waiter.wait_for_result()


async def test_wait_for_result_cancelled_status(fake_api, operation_id: str):
    queue_events_and_status(fake_api, operation_id, status=OperationStatus.CANCELLED)

    waiter = AsyncOperationWaiter(fake_api, operation_id)
    with pytest.raises(CancelledOperationError):
        await waiter.wait_for_result()


async def test_wait_for_result_without_process(fake_api, operation_id: str, result_image_uuid: UUID):
    queue_events_and_status(fake_api, operation_id, result_image_uuid=str(result_image_uuid))

    waiter = AsyncOperationWaiter(fake_api, operation_id)
    response, exit_event = await waiter.wait_for_result(spid=None)

    assert response.status == OperationStatus.SUCCESS
    assert exit_event is None


async def test_wait_for_result_missing_exit_event_raises(fake_api, operation_id: str):
    # spid 2 never gets an exit event in this canned log (only spid 1's exit fires)
    queue_events_and_status(fake_api, operation_id)

    waiter = AsyncOperationWaiter(fake_api, operation_id)
    with pytest.raises(FailedOperationError):
        await waiter.wait_for_result(spid=2)


async def test_wait_for_result_process_timed_out(fake_api, operation_id: str):
    queue_events_and_status(fake_api, operation_id, timed_out=True)

    waiter = AsyncOperationWaiter(fake_api, operation_id)
    with pytest.raises(OperationTimedOutError):
        await waiter.wait_for_result()


async def test_wait_timeout_cancels_operation(fake_api, operation_id: str):
    fake_api.mock("follow_operation_events", error=TimeoutError("no events arrived"))
    fake_api.mock("cancel_operation", None)

    waiter = AsyncOperationWaiter(fake_api, operation_id)
    with pytest.raises(OperationTimedOutError):
        await waiter.wait_for_result(timeout=0.01)

    assert fake_api.calls_for("cancel_operation")


def test_wait_timeout_cancels_operation_sync(fake_api_s, operation_id: str):
    fake_api_s.mock("follow_operation_events", error=TimeoutError("no events arrived"))
    fake_api_s.mock("cancel_operation", None)

    waiter = SyncOperationWaiter(fake_api_s, operation_id)
    with pytest.raises(OperationTimedOutError):
        waiter.wait_for_result(timeout=0.01)

    assert fake_api_s.calls_for("cancel_operation")


async def test_success_does_not_cancel_operation(fake_api, operation_id: str):
    queue_events_and_status(fake_api, operation_id)
    fake_api.mock("cancel_operation", None)

    waiter = AsyncOperationWaiter(fake_api, operation_id)
    await waiter.wait_for_result()

    assert not fake_api.calls_for("cancel_operation")


async def test_multiple_waiters_share_result(fake_api, operation_id: str):
    queue_events_and_status(fake_api, operation_id, stdout="hi\n")

    waiter = AsyncOperationWaiter(fake_api, operation_id)
    from asyncio import gather

    first, second = await gather(waiter.wait_for_result(), waiter.wait_for_result())

    assert first == second
    assert len(fake_api.calls_for("follow_operation_events")) == 1


async def test_cancel_failure_does_not_mask_original_error(fake_api, operation_id: str):
    # cancel_operation raising something other than ContreeAPIError must not
    # replace the timeout error already propagating out of the `finally`.
    fake_api.mock("follow_operation_events", error=TimeoutError("no events arrived"))
    fake_api.mock("cancel_operation", error=RuntimeError("cancel transport blew up"))

    waiter = AsyncOperationWaiter(fake_api, operation_id)
    with pytest.raises(OperationTimedOutError):
        await waiter.wait_for_result(timeout=0.01)


def test_cancel_failure_does_not_mask_original_error_sync(fake_api_s, operation_id: str):
    fake_api_s.mock("follow_operation_events", error=TimeoutError("no events arrived"))
    fake_api_s.mock("cancel_operation", error=RuntimeError("cancel transport blew up"))

    waiter = SyncOperationWaiter(fake_api_s, operation_id)
    with pytest.raises(OperationTimedOutError):
        waiter.wait_for_result(timeout=0.01)


def test_sync_iter_chunks_after_exhausted_does_not_resubscribe(fake_api_s, operation_id: str):
    queue_events_and_status(fake_api_s, operation_id, stdout="hi\n")

    waiter = SyncOperationWaiter(fake_api_s, operation_id)
    waiter.wait_for_result()
    assert waiter.process_view().outputs["stdout"] == b"hi\n"

    # A second consumer (or the same one iterating again) must not
    # re-subscribe and re-process the event log, which would double the
    # accumulated output.
    assert list(waiter.iter_chunks(MAIN_SPID, timeout=None)) == []
    assert len(fake_api_s.calls_for("follow_operation_events")) == 1
    assert waiter.process_view().outputs["stdout"] == b"hi\n"


async def test_output_limit_caps_accumulated_buffer(fake_api, operation_id: str):
    waiter = AsyncOperationWaiter(fake_api, operation_id, output_limit=4)
    buffer = BytesIO()
    await waiter.connect_output(output=buffer, spid=MAIN_SPID, stream_name="stdout")
    for event in run_events(stdout="hello world"):
        if event.type == "stdout":
            await waiter.process_event(event)

    assert bytes(waiter.outputs[MAIN_SPID]["stdout"]) == b"hell"
    assert buffer.getvalue() == b"hello world"


def test_output_limit_caps_accumulated_buffer_sync(fake_api_s, operation_id: str):
    waiter = SyncOperationWaiter(fake_api_s, operation_id, output_limit=4)
    buffer = BytesIO()
    waiter.connect_output(output=buffer, spid=MAIN_SPID, stream_name="stdout")
    for event in run_events(stdout="hello world"):
        if event.type == "stdout":
            waiter.process_event(event)

    assert bytes(waiter.outputs[MAIN_SPID]["stdout"]) == b"hell"
    assert buffer.getvalue() == b"hello world"


async def test_connect_output_after_finish(fake_api, operation_id: str):
    queue_events_and_status(fake_api, operation_id, stdout="hi\n")

    waiter = AsyncOperationWaiter(fake_api, operation_id)
    await waiter.wait_for_result()

    buffer = BytesIO()
    await waiter.connect_output(output=buffer, spid=MAIN_SPID, stream_name="stdout")
    assert buffer.getvalue() == b"hi\n"
