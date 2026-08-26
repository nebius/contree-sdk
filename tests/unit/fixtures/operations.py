from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

import pytest
from contree_client.models import (
    EventDataCompletion,
    EventDataExit,
    EventDataStream,
    EventResources,
    InstanceSpawnResponse,
    OperationEvent,
    OperationResponse,
    OperationStatus,
)

from contree_sdk.sdk.objects.image_like.waiter_common import MAIN_SPID


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)

ZERO_RESOURCES = EventResources(
    user_time_us=0,
    sys_time_us=0,
    max_rss_kb=0,
    shared_memory=0,
    unshared_memory=0,
    swaps=0,
    minor_faults=0,
    major_faults=0,
    voluntary_ctx_switches=0,
    involuntary_ctx_switches=0,
    block_input_ops=0,
    block_output_ops=0,
    ipc_msgs_sent=0,
    ipc_msgs_received=0,
    signals_received=0,
)


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


def stream_event(
    event_id: int, stream: Literal["stdout", "stderr"], text: str, *, spid: int = MAIN_SPID
) -> OperationEvent:
    return OperationEvent(id=event_id, ts=NOW, type=stream, spid=spid, data=EventDataStream.from_text(text))


def exit_event(
    event_id: int,
    *,
    spid: int = MAIN_SPID,
    code: int = 0,
    signal: int = -1,
    timed_out: bool = False,
    duration_ms: int = 10,
) -> OperationEvent:
    return OperationEvent(
        id=event_id,
        ts=NOW,
        type="exit",
        spid=spid,
        data=EventDataExit(
            pid=spid, code=code, signal=signal, timed_out=timed_out, duration_ms=duration_ms, resources=ZERO_RESOURCES
        ),
    )


def completion_event(
    event_id: int,
    *,
    status: OperationStatus = OperationStatus.SUCCESS,
    result_image_uuid: str | None = None,
    error: str | None = None,
    duration_ms: int = 10,
) -> OperationEvent:
    return OperationEvent(
        id=event_id,
        ts=NOW,
        type="completion",
        data=EventDataCompletion(
            status=status, duration_ms=duration_ms, result_image_uuid=result_image_uuid, error=error
        ),
    )


def run_events(
    *,
    stdout: str = "",
    stderr: str = "",
    exit_code: int = 0,
    signal: int = -1,
    timed_out: bool = False,
    status: OperationStatus = OperationStatus.SUCCESS,
    result_image_uuid: str | None = None,
    error: str | None = None,
) -> list[OperationEvent]:
    """Build a canned event log for one run: [stdout] [stderr] exit completion."""
    events: list[OperationEvent] = []
    for name, content in (("stdout", stdout), ("stderr", stderr)):
        if content:
            events.append(stream_event(len(events), name, content))
    events.append(exit_event(len(events), code=exit_code, signal=signal, timed_out=timed_out))
    events.append(completion_event(len(events), status=status, result_image_uuid=result_image_uuid, error=error))
    return events


def queue_run(
    api: Any,
    *,
    operation_id: str | None = None,
    stdout: str = "",
    stderr: str = "",
    exit_code: int = 0,
    timed_out: bool = False,
    status: OperationStatus = OperationStatus.SUCCESS,
    result_image_uuid: str | None = None,
    error: str | None = None,
) -> str:
    """Queue one full spawn -> events -> status cycle on a contree_client testing double."""
    operation_id = operation_id or str(uuid4())
    api.mock("spawn_instance", InstanceSpawnResponse(uuid=operation_id))
    api.mock(
        "follow_operation_events",
        run_events(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            timed_out=timed_out,
            status=status,
            result_image_uuid=result_image_uuid,
            error=error,
        ),
    )
    api.mock(
        "get_operation_status",
        OperationResponse(uuid=operation_id, status=status, result_image_uuid=result_image_uuid, error=error),
    )
    return operation_id
