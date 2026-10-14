"""Typed build notifications and per-build event state."""

import time
from dataclasses import dataclass
from typing import Literal

from contree_client.models import InstanceResult


BuildEventType = Literal[
    "step_started", "operation_started", "stdout", "stderr", "cache_hit", "step_completed", "step_failed"
]


@dataclass(frozen=True)
class BuildStep:
    """One directive execution; IDs start at zero within each build.

    index is the parsed Dockerfile position, or None for a synthetic step.
    parent_id identifies the enclosing directive for nested execution.
    """

    id: int
    keyword: str
    index: int | None = None
    parent_id: int | None = None


@dataclass(frozen=True, kw_only=True)
class BuildEvent:
    """A build notification with raw output bytes and the current operation identity.

    result is available after the operation finishes, including nonzero exits.
    Errors retain their original exception object. Output is never decoded or formatted.
    """

    type: BuildEventType
    step: BuildStep
    operation_uuid: str | None = None
    image_before: str | None = None
    image_after: str | None = None
    duration: float = 0.0
    data: bytes = b""
    result: InstanceResult | None = None
    error: BaseException | None = None


@dataclass
class BuildFrame:
    step: BuildStep
    started: float
    image_before: str | None
    operation_uuid: str | None = None
    result: InstanceResult | None = None


@dataclass
class BuildProgress:
    sequence: int = 0
    current: BuildFrame | None = None

    def start(self, keyword: str, index: int | None, image: str | None) -> None:
        parent = self.current.step.id if self.current is not None else None
        self.current = BuildFrame(BuildStep(self.sequence, keyword, index, parent), time.monotonic(), image)
        self.sequence += 1

    def event(
        self, event_type: BuildEventType, image: str | None, *, data: bytes = b"", error: BaseException | None = None
    ) -> BuildEvent | None:
        if self.current is None:
            return None
        frame = self.current
        return BuildEvent(
            type=event_type,
            step=frame.step,
            operation_uuid=frame.operation_uuid,
            image_before=frame.image_before,
            image_after=image,
            duration=time.monotonic() - frame.started,
            data=data,
            result=frame.result,
            error=error,
        )
