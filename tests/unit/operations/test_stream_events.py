import re
from datetime import datetime, timezone
from uuid import UUID

import pytest
from pytest_httpx import HTTPXMock

from contree_sdk import Contree
from contree_sdk._internals.models.operation import OperationEvent, OperationEventType
from contree_sdk.sdk.exceptions.api import MalformedEventError
from contree_sdk.utils.models.operation import OperationStatus
from tests.unit.fixtures.operations import add_events_responses, sse_event


async def _collect(contree: Contree, operation_id: str, **kwargs) -> list[OperationEvent]:
    return [event async for event in contree._api.stream_operation_events(operation_id, **kwargs)]


async def test_stream_events_parsed(fake_contree: Contree, operation_id: str, strict_httpx: HTTPXMock):
    add_events_responses(
        strict_httpx,
        operation_id,
        sse_event(1, "stdout", {"text": "hi"}, spid=5),
        sse_event(2),
    )

    first, last = await _collect(fake_contree, operation_id)

    assert first == OperationEvent(
        id=1,
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        type=OperationEventType.STDOUT,
        data={"text": "hi"},
        spid=5,
    )
    assert last.id == 2
    assert last.type == OperationEventType.COMPLETION
    assert last.spid is None


async def test_stream_events_query_params(fake_contree: Contree, operation_id: str, strict_httpx: HTTPXMock):
    add_events_responses(strict_httpx, operation_id)

    assert await _collect(fake_contree, operation_id, follow=False, since=5) == []

    [request] = strict_httpx.get_requests()
    assert request.url.params["follow"] == "0"
    assert request.url.params["since"] == "5"


async def test_stream_events_frame_without_trailing_separator(
    fake_contree: Contree, operation_id: str, strict_httpx: HTTPXMock
):
    add_events_responses(strict_httpx, operation_id, sse_event(7).rstrip(b"\n"))

    [event] = await _collect(fake_contree, operation_id)
    assert event.id == 7


@pytest.mark.parametrize(
    "frame",
    [
        b"data: {broken json\n\n",
        b"id: 1\n\n",
        b"line without delimiter\n\n",
    ],
)
async def test_stream_events_malformed(fake_contree: Contree, operation_id: str, strict_httpx: HTTPXMock, frame: bytes):
    add_events_responses(strict_httpx, operation_id, frame)

    with pytest.raises(MalformedEventError):
        await _collect(fake_contree, operation_id)


def _completion_frame(event_id: int, result_image_uuid: UUID) -> bytes:
    completion_data = {
        "status": str(OperationStatus.SUCCESS),
        "result_image_uuid": str(result_image_uuid),
        "duration_ms": 500,
    }
    return sse_event(event_id, "completion", completion_data)


async def test_wait_operation_over_stream(
    fake_contree: Contree, operation_id: str, result_image_uuid: UUID, strict_httpx: HTTPXMock
):
    add_events_responses(strict_httpx, operation_id, sse_event(1, "init"), _completion_frame(2, result_image_uuid))

    completion, _ = await fake_contree._wait_operation(operation_id, spid=None)

    assert completion.status == OperationStatus.SUCCESS
    assert completion.result_image_uuid == str(result_image_uuid)


async def test_wait_operation_resumes_stream_after_last_event(
    fake_contree: Contree, operation_id: str, result_image_uuid: UUID, strict_httpx: HTTPXMock
):
    add_events_responses(strict_httpx, operation_id, sse_event(1, "init"), sse_event(2, "spawn"))
    add_events_responses(strict_httpx, operation_id, _completion_frame(3, result_image_uuid))

    await fake_contree._wait_operation(operation_id, spid=None)

    events_requests = [r for r in strict_httpx.get_requests() if r.url.path.endswith("/events")]
    assert [r.url.params["since"] for r in events_requests] == ["-1", "2"]


async def test_wait_operation_survives_stream_errors(
    fake_contree: Contree, operation_id: str, result_image_uuid: UUID, strict_httpx: HTTPXMock
):
    strict_httpx.add_response(
        method="GET",
        url=re.compile(f".*/operations/{operation_id}/events.*"),
        status_code=404,
        json={"error": "Operation not found", "status": 404},
    )
    add_events_responses(strict_httpx, operation_id, _completion_frame(1, result_image_uuid))

    completion, _ = await fake_contree._wait_operation(operation_id, spid=None)

    assert completion.result_image_uuid == str(result_image_uuid)
