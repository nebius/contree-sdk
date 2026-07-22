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


@pytest.fixture
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
    stderr_content: str = "this is stderr\n",
) -> OperationModel:
    execution_result = ProcessExecutionResult(
        stdout=io_encode(stdout_content, StreamEncoding.base64),
        stderr=io_encode(stderr_content, StreamEncoding.base64),
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
        preserve_env=True,
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
    stderr_content: str = "this is stderr\n",
    not_found_first: bool = False,
):
    pending_op = create_operation_model(
        image_uuid,
        result_image_uuid,
        process_state,
        resource_usage,
        stdout_content,
        OperationStatus.PENDING,
        0.0,
        stderr_content,
    )
    success_op = create_operation_model(
        image_uuid,
        result_image_uuid,
        process_state,
        resource_usage,
        stdout_content,
        OperationStatus.SUCCESS,
        0.5,
        stderr_content,
    )
    operation_url = re.compile(f".*/operations/{operation_id}")
    if not_found_first:
        httpx_mock.add_response(
            status_code=404,
            is_optional=True,
            json={"error": "Operation not found", "status": 404},
        )

    httpx_mock.add_response(
        method="GET",
        url=operation_url,
        json=asdict(pending_op),
        is_optional=True,
    )
    httpx_mock.add_response(
        method="GET",
        url=operation_url,
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
            json={"files": files_list},
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
