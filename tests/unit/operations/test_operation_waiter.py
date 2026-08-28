from asyncio import CancelledError, Event, create_task, gather, sleep, wait_for
from dataclasses import replace
from datetime import timedelta
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from contree_client.models import EventResources
from pytest_httpx import HTTPXMock

from contree_sdk import Contree
from contree_sdk._internals.io.operation_waiter import MAIN_SPID
from contree_sdk.sdk.exceptions import (
    CancelledOperationError,
    EventStreamInterruptedError,
    FailedOperationError,
    GoneError,
    MalformedEventError,
    OperationTimedOutError,
)
from contree_sdk.utils.models.operation import OperationStatus
from tests.unit.fixtures.operations import (
    ProcessState,
    SlowEventStream,
    add_events_responses,
    run_event_frames,
    sse_event,
)
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
    resource_usage: EventResources,
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


async def test_wait_for_result_bounds_local_output_and_records_local_truncation(
    fake_contree: Contree,
    operation_id: str,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: EventResources,
    strict_httpx: HTTPXMock,
):
    fake_contree.config.default_truncate_output_at = 5
    frames = run_event_frames(result_image_uuid, process_state, resource_usage, "abcdefgh", "123456")
    add_events_responses(strict_httpx, operation_id, *frames)

    waiter = await fake_contree._get_operation_waiter(operation_id)
    await waiter.wait_for_result()

    view = waiter.process_view()
    assert view.outputs == {"stdout": b"abcde", "stderr": b"12345"}
    assert view.truncated["stdout"].bytes_emitted == 5
    assert view.truncated["stdout"].bytes_dropped == 3
    assert view.truncated["stderr"].bytes_emitted == 5
    assert view.truncated["stderr"].bytes_dropped == 1
    assert waiter._truncated[MAIN_SPID] == {}


async def test_wait_for_result_failed(
    fake_contree: Contree,
    operation_id: str,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: EventResources,
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
    resource_usage: EventResources,
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
    resource_usage: EventResources,
    strict_httpx: HTTPXMock,
):
    timed_out_state = replace(process_state, timed_out=True)
    frames = run_event_frames(result_image_uuid, timed_out_state, resource_usage, "", "")
    add_events_responses(strict_httpx, operation_id, *frames)

    waiter = await fake_contree._get_operation_waiter(operation_id)
    with pytest.raises(OperationTimedOutError):
        await waiter.wait_for_result()


async def test_malformed_stream_event_is_fatal_and_not_retried(
    fake_contree: Contree, operation_id: str, strict_httpx: HTTPXMock
):
    add_events_responses(strict_httpx, operation_id, sse_event(1, "stdout", {"encoding": "utf-8"}, spid=MAIN_SPID))
    strict_httpx.add_response(
        method="DELETE",
        url=r(".*/operations/.*"),
        json={},
        is_optional=True,
    )

    waiter = await fake_contree._get_operation_waiter(operation_id)
    with pytest.raises(MalformedEventError):
        await waiter.wait_for_result()

    events_requests = [request for request in strict_httpx.get_requests() if request.url.path.endswith("/events")]
    assert len(events_requests) == 1


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
    resource_usage: EventResources,
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
    resource_usage: EventResources,
    strict_httpx: HTTPXMock,
):
    frames = run_event_frames(result_image_uuid, process_state, resource_usage, "", "")
    add_events_responses(strict_httpx, operation_id, *frames)

    waiter = await fake_contree._get_operation_waiter(operation_id)
    first, second = await gather(waiter.wait_for_result(), waiter.wait_for_result())

    assert first == second
    events_requests = [request for request in strict_httpx.get_requests() if request.url.path.endswith("/events")]
    assert len(events_requests) == 1


async def test_concurrent_operations_do_not_share_stream_retry_state(fake_contree: Contree, operation_id: str):
    first_waiter = await fake_contree._get_operation_waiter(operation_id)
    second_waiter = await fake_contree._get_operation_waiter(uuid4())
    assert first_waiter._stream_retrier is not second_waiter._stream_retrier

    first_waiter._stream_retrier.retry_interval_min = timedelta(0)
    first_waiter._stream_retrier.retry_interval_max = timedelta(0)
    retry_started = Event()
    release_retry = Event()
    attempts = 0

    async def hold_retried_stream() -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise EventStreamInterruptedError(error="test retry")
        retry_started.set()
        await release_retry.wait()

    async def complete_other_stream() -> None:
        return None

    first_task = create_task(first_waiter._stream_retrier(hold_retried_stream))
    try:
        await wait_for(retry_started.wait(), timeout=1)
        await wait_for(second_waiter._stream_retrier(complete_other_stream), timeout=1)
    finally:
        release_retry.set()
        await first_task

    assert attempts == 2


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
    resource_usage: EventResources,
    strict_httpx: HTTPXMock,
):
    frames = run_event_frames(result_image_uuid, process_state, resource_usage, "hi\n", "")
    add_events_responses(strict_httpx, operation_id, *frames)

    waiter = await fake_contree._get_operation_waiter(operation_id)
    await waiter.wait_for_result()

    buffer = BytesIO()
    await waiter.connect_output(output=buffer, spid=MAIN_SPID, stream_name="stdout")
    assert buffer.getvalue() == b"hi\n"


async def test_iter_chunks_after_finish_does_not_deadlock(
    fake_contree: Contree,
    operation_id: str,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: EventResources,
    strict_httpx: HTTPXMock,
):
    frames = run_event_frames(result_image_uuid, process_state, resource_usage, "hi\n", "oops\n")
    add_events_responses(strict_httpx, operation_id, *frames)
    waiter = await fake_contree._get_operation_waiter(operation_id)
    await waiter.wait_for_result()

    async def collect_chunks():
        return [chunk async for chunk in waiter.iter_chunks(MAIN_SPID)]

    chunks = await wait_for(collect_chunks(), timeout=1)
    assert {(chunk.stream_name, chunk.value) for chunk in chunks} == {
        ("stdout", b"hi\n"),
        ("stderr", b"oops\n"),
    }


async def test_cancelling_chunk_iteration_disconnects_queue_writers(fake_contree: Contree, operation_id: str):
    waiter = await fake_contree._get_operation_waiter(operation_id)
    iterator = waiter.iter_chunks(MAIN_SPID)
    pending_chunk = create_task(anext(iterator))
    await sleep(0)
    assert waiter._readers_by_spid

    pending_chunk.cancel()
    await gather(pending_chunk, return_exceptions=True)

    assert not any(waiter._readers_by_spid.values())
