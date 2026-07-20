import re
from collections.abc import Iterator
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from pytest_httpx import HTTPXMock, IteratorStream

from contree_sdk.utils.models.operation import OperationStatus
from tests.unit.fixtures.operations import add_base_responses, add_events_responses, sse_event
from tests.unit.fixtures.utils import r


def import_event_frames(result_image_uuid: UUID, status: OperationStatus) -> tuple[bytes, ...]:
    completion_data = {
        "status": str(status),
        "result_image_uuid": str(result_image_uuid) if status == OperationStatus.SUCCESS else None,
        "error": "Import failed" if status == OperationStatus.FAILED else None,
        "duration_ms": 500,
    }
    return (sse_event(0, "init", spid=0), sse_event(1, "completion", completion_data))


def pending_then(frames: tuple[bytes, ...], pending_seconds: float) -> Iterator[bytes]:
    deadline = monotonic() + pending_seconds
    while monotonic() < deadline:
        sleep(0.05)
        yield b": keepalive\n\n"
    yield from frames


def add_import_operation_responses(
    httpx_mock: HTTPXMock,
    operation_id: str,
    result_image_uuid: UUID,
    pending_count: int = 1,
    final_status: OperationStatus = OperationStatus.SUCCESS,
    final_count: int = 1,
):
    frames = import_event_frames(result_image_uuid, final_status)
    if pending_count > 1:
        httpx_mock.add_response(
            method="GET",
            url=re.compile(f".*/operations/{operation_id}/events.*"),
            stream=IteratorStream(pending_then(frames, pending_seconds=pending_count * 0.1)),
            is_optional=True,
        )
    add_events_responses(httpx_mock, operation_id, *frames, is_reusable=True)


def add_failed_import_operation_responses(
    httpx_mock: HTTPXMock,
    operation_id: str,
    result_image_uuid: UUID,
):
    add_import_operation_responses(
        httpx_mock, operation_id, result_image_uuid, pending_count=1, final_status=OperationStatus.FAILED
    )


def add_cancelled_import_operation_responses(
    httpx_mock: HTTPXMock,
    operation_id: str,
    result_image_uuid: UUID,
):
    add_import_operation_responses(
        httpx_mock, operation_id, result_image_uuid, pending_count=10, final_status=OperationStatus.CANCELLED
    )


def add_import_operation(
    httpx_mock: HTTPXMock,
    operation_id: str,
    result_image_uuid: UUID,
    pending_count: int = 1,
    final_status: OperationStatus = OperationStatus.SUCCESS,
    final_count: int = 1,
):
    httpx_mock.add_response(
        method="POST",
        url=r(".*/images/import"),
        json={"uuid": operation_id},
        is_optional=True,
    )
    add_base_responses(httpx_mock, operation_id)
    add_import_operation_responses(
        httpx_mock, operation_id, result_image_uuid, pending_count, final_status, final_count
    )


@pytest.fixture
def api_fake_import(result_image_uuid: UUID, strict_httpx: HTTPXMock) -> HTTPXMock:
    add_import_operation(strict_httpx, str(uuid4()), result_image_uuid)
    return strict_httpx


@pytest.fixture
def api_fake_import_failed(result_image_uuid: UUID, strict_httpx: HTTPXMock) -> HTTPXMock:
    add_import_operation(strict_httpx, str(uuid4()), result_image_uuid, final_status=OperationStatus.FAILED)
    return strict_httpx


@pytest.fixture
def api_fake_import_cancel(result_image_uuid: UUID, strict_httpx: HTTPXMock) -> HTTPXMock:
    add_import_operation(
        strict_httpx, str(uuid4()), result_image_uuid, pending_count=10, final_status=OperationStatus.CANCELLED
    )
    return strict_httpx


@pytest.fixture
def api_fake_import_slow(result_image_uuid: UUID, httpx_mock: HTTPXMock) -> HTTPXMock:
    add_import_operation(
        httpx_mock,
        str(uuid4()),
        result_image_uuid,
        pending_count=7,
        final_status=OperationStatus.CANCELLED,
        final_count=5,
    )
    return httpx_mock
