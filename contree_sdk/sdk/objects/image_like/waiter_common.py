from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from contree_client.models import EventDataExit, EventDataTruncated, EventResources


MAIN_SPID = 1

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


def synthetic_exit_event(*, pid: int, duration_ms: int) -> EventDataExit:
    """Stand in for the exit event the fallback transport never sends.

    Used when the events endpoint is unavailable and the transport only
    synthesizes a `completion` event. The operation is known to have
    actually succeeded at this point (its status is checked before this
    is ever called) -- there is just no exit detail to report, so this
    reports a clean, non-timed-out, no-signal exit with an
    unknown-but-successful code.

    Returns:
        A synthetic `EventDataExit` standing in for the missing one.

    """
    return EventDataExit(
        pid=pid,
        code=0,
        signal=-1,
        timed_out=False,
        duration_ms=duration_ms,
        resources=ZERO_RESOURCES,
    )


StreamName = Literal["stdout", "stderr"]
STREAM_NAMES: tuple[StreamName, ...] = ("stdout", "stderr")


@dataclass
class OutputChunk:
    value: bytes
    stream_name: StreamName


@dataclass
class ProcessView:
    exit: EventDataExit | None
    outputs: dict[StreamName, bytes]
    truncated: dict[str, EventDataTruncated]
