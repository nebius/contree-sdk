import asyncio
import json
import re
from collections.abc import AsyncIterator, Iterator
from dataclasses import asdict, dataclass
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from contree_client.models import EventResources
from httpx import AsyncByteStream, SyncByteStream
from pytest_httpx import HTTPXMock, IteratorStream

from contree_sdk._internals.io.codecs import io_encode
from contree_sdk._internals.io.operation_waiter import MAIN_SPID
from contree_sdk.utils.models.operation import OperationStatus
from contree_sdk.utils.models.stream import StreamEncoding
from tests.unit.fixtures.utils import r


OPERATION_COST = 12.34


@dataclass
class ProcessState:
    continued: bool
    core_dump: bool
    exit_code: int
    pid: int
    signal: int
    stopped: bool
    timed_out: bool


@pytest.fixture
def operation_id() -> str:
    return str(uuid4())


def sse_event(
    event_id: int, event_type: str = "completion", data: dict | None = None, spid: int | None = None
) -> bytes:
    payload = {"id": event_id, "ts": "2026-01-01T00:00:00Z", "type": event_type, "data": data or {}}
    if spid is not None:
        payload["spid"] = spid
    return f"id: {event_id}\nevent: {event_type}\ndata: {json.dumps(payload)}\n\n".encode()


class SlowEventStream(AsyncByteStream, SyncByteStream):
    def __init__(self, frames: tuple[bytes, ...] = (), pending_seconds: float = 5.0):
        self._frames = frames
        self._pending_seconds = pending_seconds

    def __iter__(self) -> Iterator[bytes]:
        deadline = monotonic() + self._pending_seconds
        while monotonic() < deadline:
            sleep(0.05)
            yield b": keepalive\n\n"
        yield from self._frames

    async def __aiter__(self) -> AsyncIterator[bytes]:
        deadline = monotonic() + self._pending_seconds
        while monotonic() < deadline:
            await asyncio.sleep(0.05)
            yield b": keepalive\n\n"
        for frame in self._frames:
            yield frame


def add_events_responses(
    httpx_mock: HTTPXMock,
    operation_id: str = "[^/]+",
    *frames: bytes,
    is_reusable: bool = False,
):
    httpx_mock.add_response(
        method="GET",
        url=re.compile(f".*/operations/{operation_id}/events.*"),
        stream=IteratorStream(frames),
        is_optional=True,
        is_reusable=is_reusable,
    )


def run_event_frames(
    result_image_uuid: UUID | None,
    process_state: ProcessState,
    resource_usage: EventResources,
    stdout_content: str,
    stderr_content: str,
    status: OperationStatus = OperationStatus.SUCCESS,
) -> tuple[bytes, ...]:
    frames = [sse_event(0, "init", spid=0)]
    for stream_name, content in (("stdout", stdout_content), ("stderr", stderr_content)):
        if content:
            frames.append(
                sse_event(len(frames), stream_name, asdict(io_encode(content, StreamEncoding.base64)), spid=MAIN_SPID)
            )
    exit_data = {
        "code": process_state.exit_code,
        "duration_ms": 500,
        "pid": process_state.pid,
        "signal": process_state.signal,
        "timed_out": process_state.timed_out,
        "resources": resource_usage.to_dict(),
    }
    frames.append(sse_event(len(frames), "exit", exit_data, spid=MAIN_SPID))
    completion_data = {
        "status": str(status),
        "result_image_uuid": str(result_image_uuid) if result_image_uuid else None,
        "error": None,
        "duration_ms": 500,
    }
    frames.append(sse_event(len(frames), "completion", completion_data))
    return tuple(frames)


def add_operation_responses(
    httpx_mock: HTTPXMock,
    operation_id: str,
    image_uuid: UUID,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: EventResources,
    stdout_content: str = "my input\nthis is stdout\n",
    stderr_content: str = "this is stderr\n",
    not_found_first: bool = False,
):
    if not_found_first:
        httpx_mock.add_response(
            method="GET",
            url=re.compile(f".*/operations/{operation_id}/events.*"),
            status_code=404,
            is_optional=True,
            json={"error": "Operation not found", "status": 404},
        )
    frames = run_event_frames(result_image_uuid, process_state, resource_usage, stdout_content, stderr_content)
    add_events_responses(httpx_mock, operation_id, *frames, is_reusable=True)
    add_operation_status_response(httpx_mock, operation_id, image_uuid, OPERATION_COST)


def add_operation_status_response(
    httpx_mock: HTTPXMock,
    operation_id: str,
    image_uuid: UUID,
    cost: float,
):
    httpx_mock.add_response(
        method="GET",
        url=re.compile(f".*/operations/{operation_id}$"),
        json={
            "uuid": operation_id,
            "kind": "instance",
            "status": "SUCCESS",
            "metadata": {
                "command": "true",
                "image": str(image_uuid),
                "result": {"resources": {"cost": cost}},
            },
        },
        is_optional=True,
    )


@pytest.fixture
def api_fake_streamed_run(
    result_image_uuid: UUID,
    operation_id: str,
    process_state: ProcessState,
    resource_usage: EventResources,
    strict_httpx: HTTPXMock,
) -> HTTPXMock:
    add_base_responses(strict_httpx, operation_id)
    frames = run_event_frames(result_image_uuid, process_state, resource_usage, "streamed\n", "")
    add_events_responses(strict_httpx, operation_id, *frames)
    add_events_responses(strict_httpx, operation_id, *frames)
    add_events_responses(strict_httpx, operation_id, *frames[1:])
    add_operation_status_response(strict_httpx, operation_id, result_image_uuid, OPERATION_COST)
    return strict_httpx


def add_base_responses(httpx_mock: HTTPXMock, operation_id: str):
    httpx_mock.add_response(
        method="POST",
        url=r(".*/instances"),
        json={"uuid": operation_id},
        is_optional=True,
    )
    httpx_mock.add_response(
        method="DELETE",
        url=r(".*/operations/.*"),
        json={},
        is_optional=True,
    )
    httpx_mock.add_response(
        method="GET",
        url=r(".*/inspect/[^/]+/$"),
        json={"uuid": str(uuid4()), "tag": None, "created_at": "2024-01-01T12:00:00+00:00"},
        is_optional=True,
    )


def add_inspect_list_responses(
    httpx_mock: HTTPXMock,
    count: int = 5,
    files_list: list | None = None,
):
    from tests.unit.images.test_inspect import create_file_item

    if files_list is None:
        files_list = [create_file_item("f.txt", is_dir=False, size=10)]

    for _ in range(count):
        httpx_mock.add_response(
            method="GET",
            url=r(".*/inspect/.*/list.*"),
            json={"path": "/", "files": files_list},
            is_optional=True,
        )


def add_inspect_download_responses(
    httpx_mock: HTTPXMock,
    count: int = 10,
    content: bytes = b"data",
):
    for _ in range(count):
        httpx_mock.add_response(
            method="GET",
            url=r(".*/inspect/.*/download.*"),
            content=content,
            is_optional=True,
        )


def add_inspect_list_download_responses(
    httpx_mock: HTTPXMock,
    list_count: int = 5,
    download_count: int = 10,
):
    add_inspect_list_responses(httpx_mock, list_count)
    add_inspect_download_responses(httpx_mock, download_count)
