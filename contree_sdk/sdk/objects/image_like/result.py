from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from contree_client.models import EventDataExit, EventDataTruncated, OperationInstanceMetadata, OperationResponse

from contree_sdk.sdk.io.typing import OUTPUT_TYPES
from contree_sdk.utils.sentinels import value_or_none


def extract_operation_cost(operation_data: OperationResponse) -> float | None:
    """Pull the cost figure out of a `get_operation_status` response, if present.

    The exit event itself (`EventDataExit`/`EventResources`) carries no cost
    field, but `OperationResponse.metadata.result.resources.cost` does for
    instance operations -- `wait_for_result` already fetches this response,
    so no extra API call is needed here.

    Returns:
        The operation's cost, or `None` if unavailable.

    """
    metadata = value_or_none(operation_data.metadata)
    if not isinstance(metadata, OperationInstanceMetadata):
        return None
    result = value_or_none(metadata.result)
    if result is None:
        return None
    resources = value_or_none(result.resources)
    if resources is None:
        return None
    return value_or_none(resources.cost)


@dataclass(frozen=True)
class ContreeResult:
    stderr: OUTPUT_TYPES | None
    stdout: OUTPUT_TYPES | None
    exit_code: int
    elapsed_time: timedelta
    truncated: dict[str, EventDataTruncated]
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
            cost=cost,
            raw=raw_result,
        )
