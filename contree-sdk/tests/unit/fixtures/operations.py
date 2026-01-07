import re
from dataclasses import asdict
from uuid import UUID, uuid4

import pytest
from pytest_httpx import HTTPXMock

from contree_sdk._internals.models.instance import (
    InstanceOperationMetadata,
    InstanceOperationResult,
    ProcessExecutionResult,
    ProcessResources,
    ProcessState,
)
from contree_sdk._internals.models.operation import OperationKind, OperationModel
from contree_sdk.utils.codecs import io_encode
from contree_sdk.utils.models.operation import OperationStatus
from contree_sdk.utils.models.stream import StreamDescription, StreamEncoding
from tests.unit.fixtures.utils import r


@pytest.fixture()
def operation_id() -> str:
    return str(uuid4())


def create_operation_model(
    image_uuid: UUID,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    stdout_content: str,
    status: OperationStatus,
    duration: float = 0.0,
) -> OperationModel:
    execution_result = ProcessExecutionResult(
        stdout=io_encode(stdout_content, StreamEncoding.base64),
        stderr=io_encode("this is stderr\n", StreamEncoding.base64),
        state=process_state,
        resources=resource_usage,
    )

    metadata = InstanceOperationMetadata(
        args=[],
        command="",
        cwd="/",
        disposable=True,
        env={},
        files={},
        hostname="",
        image=str(image_uuid),
        shell=True,
        stdin=StreamDescription(value="", encoding=StreamEncoding.ascii),
        timeout=60,
        truncate_output_at=65535,
        result=execution_result,
    )

    return OperationModel(
        kind=OperationKind.INSTANCE,
        status=status,
        duration=duration,
        metadata=metadata,
        result=InstanceOperationResult(image=str(result_image_uuid), tag=None),
    )


def add_operation_responses(
    httpx_mock: HTTPXMock,
    operation_id: str,
    image_uuid: UUID,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    stdout_content: str = "my input\nthis is stdout\n",
):
    pending_op = create_operation_model(
        image_uuid, result_image_uuid, process_state, resource_usage, stdout_content, OperationStatus.PENDING
    )
    success_op = create_operation_model(
        image_uuid, result_image_uuid, process_state, resource_usage, stdout_content, OperationStatus.SUCCESS, 0.5
    )

    httpx_mock.add_response(
        method="GET",
        url=re.compile(f".*/operations/{operation_id}"),
        json=asdict(pending_op),
        is_optional=True,
    )
    httpx_mock.add_response(
        method="GET",
        url=re.compile(f".*/operations/{operation_id}"),
        json=asdict(success_op),
        is_optional=True,
    )


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
        url=r(".*/inspect/[^/]+$"),
        json={"uuid": str(uuid4()), "tag": None, "created_at": "2024-01-01T12:00:00+00:00"},
        is_optional=True,
    )
