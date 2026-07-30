from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from contree_client.models import EventDataExit, EventDataTruncated

from contree_sdk._internals.io.typing import OUTPUT_TYPES


@dataclass(frozen=True)
class ContreeResult:
    stderr: OUTPUT_TYPES | None
    stdout: OUTPUT_TYPES | None
    exit_code: int
    elapsed_time: timedelta
    truncated: dict[str, EventDataTruncated]
    cost: float | None = field(repr=False)

    _raw: EventDataExit | None = field(repr=False)

    @classmethod
    def from_result(
        cls,
        raw_result: EventDataExit,
        *,
        stdout: OUTPUT_TYPES | None,
        stderr: OUTPUT_TYPES | None,
        truncated: dict[str, EventDataTruncated],
    ) -> ContreeResult:
        return cls(
            exit_code=raw_result.code,
            stdout=stdout,
            stderr=stderr,
            elapsed_time=timedelta(milliseconds=raw_result.duration_ms),
            truncated=truncated,
            cost=raw_result.resources.to_dict().get("cost"),
            _raw=raw_result,
        )
