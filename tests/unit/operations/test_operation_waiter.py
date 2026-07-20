from asyncio import CancelledError, create_task, gather, sleep
from dataclasses import replace
from io import BytesIO
from uuid import UUID

import pytest
from pytest_httpx import HTTPXMock

from contree_sdk import Contree
from contree_sdk._internals.io.operation_waiter import MAIN_SPID
from contree_sdk._internals.models.instance import ProcessResources, ProcessState
from contree_sdk.sdk.exceptions import (
    CancelledOperationError,
    EventStreamInterruptedError,
    FailedOperationError,
    GoneError,
    OperationTimedOutError,
)
from contree_sdk.utils.models.operation import OperationStatus
from tests.unit.fixtures.operations import SlowEventStream, add_events_responses, run_event_frames, sse_event
from tests.unit.fixtures.utils import r


def _completion_frame(event_id: int, status: OperationStatus = OperationStatus.SUCCESS) -> bytes:
    return sse_event(event_id, "completion", {"status": str(status), "duration_ms": 500})


def _add_slow_events(httpx_mock: HTTPXMock, pending_seconds: float = 5.0):
    httpx_mock.add_response(
        method="GET",
        url=r(".*/operations/.*/events.*"),
        stream=SlowEventStream(pending_seconds=pending_seconds),
        is_optional=True,
    )
    httpx_mock.add_response(
        method="GET",
        url=r(".*/operations/.*/events.*"),
        status_code=410,
        json={"error": "Operation is gone", "status": 410},
        is_optional=True,
        is_reusable=True,
    )
    httpx_mock.add_response(
        method="DELETE",
        url=r(".*/operations/.*"),
        json={},
        is_optional=True,
        is_reusable=True,
    )


async def test_wait_for_result_success(
    fake_contree: Contree,
    operation_id: str,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    strict_httpx: HTTPXMock,
):
    frames = run_event_frames(result_image_uuid, process_state, resource_usage, "hi\n", "oops\n")
    add_events_responses(strict_httpx, operation_id, *frames)

    waiter = await fake_contree._get_operation_waiter(operation_id)
    completion, exit_event = await waiter.wait_for_result()

    assert completion.status == OperationStatus.SUCCESS
    assert completion.result_image_uuid == str(result_image_uuid)
    assert exit_event.code == process_state.exit_code

    view = waiter.process_view()
    assert view.outputs["stdout"] == b"hi\n"
    assert view.outputs["stderr"] == b"oops\n"


async def test_wait_for_result_failed(
    fake_contree: Contree,
    operation_id: str,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    strict_httpx: HTTPXMock,
):
    frames = run_event_frames(result_image_uuid, process_state, resource_usage, "", "", OperationStatus.FAILED)
    add_events_responses(strict_httpx, operation_id, *frames)

    waiter = await fake_contree._get_operation_waiter(operation_id)
    with pytest.raises(FailedOperationError):
        await waiter.wait_for_result()


async def test_wait_for_result_cancelled_status(
    fake_contree: Contree,
    operation_id: str,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    strict_httpx: HTTPXMock,
):
    frames = run_event_frames(result_image_uuid, process_state, resource_usage, "", "", OperationStatus.CANCELLED)
    add_events_responses(strict_httpx, operation_id, *frames)

    waiter = await fake_contree._get_operation_waiter(operation_id)
    with pytest.raises(CancelledOperationError):
        await waiter.wait_for_result()


async def test_wait_for_result_without_exit_event(fake_contree: Contree, operation_id: str, strict_httpx: HTTPXMock):
    add_events_responses(strict_httpx, operation_id, sse_event(0, "init"), _completion_frame(1))

    waiter = await fake_contree._get_operation_waiter(operation_id)
    with pytest.raises(EventStreamInterruptedError):
        await waiter.wait_for_result()


async def test_wait_for_result_without_process(fake_contree: Contree, operation_id: str, strict_httpx: HTTPXMock):
    add_events_responses(strict_httpx, operation_id, sse_event(0, "init"), _completion_frame(1))

    waiter = await fake_contree._get_operation_waiter(operation_id)
    completion, exit_event = await waiter.wait_for_result(spid=None)

    assert completion.status == OperationStatus.SUCCESS
    assert exit_event is None


async def test_wait_for_result_process_timed_out(
    fake_contree: Contree,
    operation_id: str,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    strict_httpx: HTTPXMock,
):
    timed_out_state = replace(process_state, timed_out=True)
    frames = run_event_frames(result_image_uuid, timed_out_state, resource_usage, "", "")
    add_events_responses(strict_httpx, operation_id, *frames)

    waiter = await fake_contree._get_operation_waiter(operation_id)
    with pytest.raises(OperationTimedOutError):
        await waiter.wait_for_result()


async def test_wait_timeout_cancels_operation(fake_contree: Contree, operation_id: str, strict_httpx: HTTPXMock):
    _add_slow_events(strict_httpx)

    waiter = await fake_contree._get_operation_waiter(operation_id)
    with pytest.raises(OperationTimedOutError):
        await waiter.wait_for_result(operation_timeout=0.2)

    assert [request for request in strict_httpx.get_requests() if request.method == "DELETE"]


async def test_cancelled_waiter_cancels_operation(fake_contree: Contree, operation_id: str, strict_httpx: HTTPXMock):
    _add_slow_events(strict_httpx)

    waiter = await fake_contree._get_operation_waiter(operation_id)
    task = create_task(waiter.wait_for_result())
    await sleep(0.1)
    task.cancel()
    with pytest.raises(CancelledError):
        await task

    assert [request for request in strict_httpx.get_requests() if request.method == "DELETE"]


async def test_success_does_not_cancel_operation(
    fake_contree: Contree,
    operation_id: str,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    strict_httpx: HTTPXMock,
):
    frames = run_event_frames(result_image_uuid, process_state, resource_usage, "", "")
    add_events_responses(strict_httpx, operation_id, *frames)

    waiter = await fake_contree._get_operation_waiter(operation_id)
    await waiter.wait_for_result()

    assert not [request for request in strict_httpx.get_requests() if request.method == "DELETE"]


async def test_multiple_waiters_share_result(
    fake_contree: Contree,
    operation_id: str,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    strict_httpx: HTTPXMock,
):
    frames = run_event_frames(result_image_uuid, process_state, resource_usage, "", "")
    add_events_responses(strict_httpx, operation_id, *frames)

    waiter = await fake_contree._get_operation_waiter(operation_id)
    first, second = await gather(waiter.wait_for_result(), waiter.wait_for_result())

    assert first == second
    events_requests = [request for request in strict_httpx.get_requests() if request.url.path.endswith("/events")]
    assert len(events_requests) == 1


async def test_cancelling_one_waiter_cancels_all(fake_contree: Contree, operation_id: str, strict_httpx: HTTPXMock):
    _add_slow_events(strict_httpx)

    waiter = await fake_contree._get_operation_waiter(operation_id)
    first = create_task(waiter.wait_for_result())
    second = create_task(waiter.wait_for_result())
    await sleep(0.1)
    first.cancel()

    with pytest.raises((CancelledOperationError, GoneError)):
        await second


async def test_connect_output_after_finish(
    fake_contree: Contree,
    operation_id: str,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    strict_httpx: HTTPXMock,
):
    frames = run_event_frames(result_image_uuid, process_state, resource_usage, "hi\n", "")
    add_events_responses(strict_httpx, operation_id, *frames)

    waiter = await fake_contree._get_operation_waiter(operation_id)
    await waiter.wait_for_result()

    buffer = BytesIO()
    await waiter.connect_output(output=buffer, spid=MAIN_SPID, stream_name="stdout")
    assert buffer.getvalue() == b"hi\n"
