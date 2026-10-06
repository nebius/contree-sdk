from datetime import datetime, timezone

from contree_client.models import (
    InstanceResult,
    InstanceResultState,
    InstanceSpawnResponse,
    OperationEvent,
    OperationInstanceMetadata,
    OperationResponse,
    OperationStatus,
    StreamRepr,
)
from contree_client.testing import ContreeAsyncClient, ContreeClient


def spawn_response(operation_uuid: str = "op-1") -> InstanceSpawnResponse:
    return InstanceSpawnResponse(uuid=operation_uuid)


def operation_response(
    *,
    operation_uuid: str = "op-1",
    image_uuid: str = "img-uuid-0",
    result_image_uuid: str | None = "img-uuid-1",
    command: str = "echo hi",
    exit_code: int = 0,
    stdout: str = "hi\n",
    stderr: str = "",
    stdout_truncated: bool = False,
    stderr_truncated: bool = False,
    status: OperationStatus = OperationStatus.SUCCESS,
    error: str | None = None,
    with_result: bool = True,
) -> OperationResponse:
    return OperationResponse(
        uuid=operation_uuid,
        kind="instance",
        status=status,
        error=error,
        result_image_uuid=result_image_uuid,
        metadata=OperationInstanceMetadata(
            command=command,
            image=image_uuid,
            result=InstanceResult(
                state=InstanceResultState(exit_code=exit_code),
                stdout=StreamRepr(value=stdout, encoding="ascii", truncated=stdout_truncated),
                stderr=StreamRepr(value=stderr, encoding="ascii", truncated=stderr_truncated),
            )
            if with_result
            else ...,
        ),
    )


def mock_completion(
    client: ContreeClient | ContreeAsyncClient,
    response: OperationResponse | None = None,
    *,
    error: BaseException | None = None,
) -> None:
    """Supply a completed event stream and its final status at the transport boundary."""
    client.mock(
        "follow_operation_events",
        [OperationEvent(id=1, ts=datetime.now(timezone.utc), type="completion", data={})],
    )
    client.mock("get_operation_status", response, error=error)
