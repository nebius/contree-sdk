from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from contree_client.models import EventDataExit, EventDataTruncated

from contree_sdk.sdk.io.typing import OUTPUT_TYPES


@dataclass(frozen=True)
class ContreeResult:
    stderr: OUTPUT_TYPES | None
    stdout: OUTPUT_TYPES | None
    exit_code: int
    elapsed_time: timedelta
    truncated: dict[str, EventDataTruncated]
    # `contree_client`'s exit-event resources (`EventResources`) carry no
    # cost figure at all -- the old API's exit event had an untyped
    # `resources` dict that happened to include one, but the new typed
    # model has no such field upstream, so this can only ever be None now.
    cost: float | None = field(repr=False)

    raw: EventDataExit | None = field(repr=False)

    @classmethod
    def from_result(
        cls,
        raw_result: EventDataExit,
        *,
        stdout: OUTPUT_TYPES | None,
        stderr: OUTPUT_TYPES | None,
        truncated: dict[str, EventDataTruncated],
        cost: float | None,
    ) -> ContreeResult:
        return cls(
            exit_code=raw_result.code,
            stdout=stdout,
            stderr=stderr,
            elapsed_time=timedelta(milliseconds=raw_result.duration_ms),
            truncated=truncated,
            cost=None,
            raw=raw_result,
        )
