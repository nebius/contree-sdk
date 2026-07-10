import re
from dataclasses import asdict
from datetime import datetime, timezone
from uuid import UUID

import pytest
from pytest_httpx import HTTPXMock

from contree_sdk import Contree
from contree_sdk._internals.models.image_import import ImageImportRequest
from contree_sdk._internals.models.operation import OperationEvent, OperationEventType
from contree_sdk.sdk.exceptions.api import MalformedEventError
from contree_sdk.utils.models.operation import OperationStatus
from tests.unit.fixtures.imports import create_import_operation_model
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


def _add_status_response(httpx_mock: HTTPXMock, operation_id: str, result_image_uuid: UUID, status: OperationStatus):
    httpx_mock.add_response(
        method="GET",
        url=re.compile(f".*/operations/{operation_id}$"),
        json=asdict(create_import_operation_model(result_image_uuid, status)),
    )


async def test_wait_operation_over_stream(
    fake_contree: Contree, operation_id: str, result_image_uuid: UUID, strict_httpx: HTTPXMock
):
    add_events_responses(strict_httpx, operation_id, sse_event(1))
    _add_status_response(strict_httpx, operation_id, result_image_uuid, OperationStatus.SUCCESS)

    metadata, result = await fake_contree._wait_operation(operation_id, ImageImportRequest)

    assert isinstance(metadata, ImageImportRequest)
    assert result.image == str(result_image_uuid)


async def test_wait_operation_resumes_stream_after_last_event(
    fake_contree: Contree, operation_id: str, result_image_uuid: UUID, strict_httpx: HTTPXMock
):
    add_events_responses(strict_httpx, operation_id, sse_event(1, "init"), sse_event(2, "spawn"))
    _add_status_response(strict_httpx, operation_id, result_image_uuid, OperationStatus.PENDING)
    add_events_responses(strict_httpx, operation_id, sse_event(3))
    _add_status_response(strict_httpx, operation_id, result_image_uuid, OperationStatus.SUCCESS)

    await fake_contree._wait_operation(operation_id, ImageImportRequest)

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
    _add_status_response(strict_httpx, operation_id, result_image_uuid, OperationStatus.SUCCESS)

    _, result = await fake_contree._wait_operation(operation_id, ImageImportRequest)

    assert result.image == str(result_image_uuid)
