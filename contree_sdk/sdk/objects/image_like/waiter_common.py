from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from contree_client.models import EventDataExit, EventDataTruncated


MAIN_SPID = 1

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
