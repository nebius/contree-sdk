import re
from dataclasses import asdict
from uuid import UUID, uuid4

import pytest
from pytest_httpx import HTTPXMock

from contree_sdk._internals.models.image_import import ImageImportRequest, PublicRegistryInfo
from contree_sdk._internals.models.instance import InstanceOperationResult, ProcessResources, ProcessState
from contree_sdk._internals.models.operation import OperationKind, OperationModel
from contree_sdk.utils.models.operation import OperationStatus
from tests.unit.fixtures.operations import add_base_responses
from tests.unit.fixtures.utils import r


def create_import_operation_model(
    result_image_uuid: UUID,
    status: OperationStatus,
    duration: float = 0.0,
) -> OperationModel:
    metadata = ImageImportRequest(
        registry=PublicRegistryInfo(url="docker://ghcr.io/linuxserver/code-server:latest"),
        tag=None,
        timeout=300,
    )

    return OperationModel(
        kind=OperationKind.IMAGE_IMPORT,
        status=status,
        duration=duration,
        metadata=metadata,
        result=InstanceOperationResult(image=str(result_image_uuid), tag="code-server:latest"),
    )


def add_import_operation_responses(
    httpx_mock: HTTPXMock,
    operation_id: str,
    result_image_uuid: UUID,
):
    pending_op = create_import_operation_model(result_image_uuid, OperationStatus.PENDING)
    success_op = create_import_operation_model(result_image_uuid, OperationStatus.SUCCESS, 0.5)

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


def add_failed_import_operation_responses(
    httpx_mock: HTTPXMock,
    operation_id: str,
    result_image_uuid: UUID,
):
    pending_op = create_import_operation_model(result_image_uuid, OperationStatus.PENDING)
    failed_op = create_import_operation_model(result_image_uuid, OperationStatus.FAILED, 0.5)

    httpx_mock.add_response(
        method="GET",
        url=re.compile(f".*/operations/{operation_id}"),
        json=asdict(pending_op),
        is_optional=True,
    )
    httpx_mock.add_response(
        method="GET",
        url=re.compile(f".*/operations/{operation_id}"),
        json=asdict(failed_op),
        is_optional=True,
    )


@pytest.fixture()
def api_fake_import(
    image_uuid: UUID,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    strict_httpx: HTTPXMock,
) -> HTTPXMock:
    operation_id = str(uuid4())

    strict_httpx.add_response(
        method="POST",
        url=r(".*/images/import"),
        json={"uuid": operation_id},
        is_optional=True,
    )

    add_base_responses(strict_httpx, operation_id)

    add_import_operation_responses(
        strict_httpx,
        operation_id,
        result_image_uuid,
    )

    return strict_httpx


@pytest.fixture()
def api_fake_import_failed(
    image_uuid: UUID,
    result_image_uuid: UUID,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    strict_httpx: HTTPXMock,
) -> HTTPXMock:
    operation_id = str(uuid4())

    strict_httpx.add_response(
        method="POST",
        url=r(".*/images/import"),
        json={"uuid": operation_id},
        is_optional=True,
    )

    add_base_responses(strict_httpx, operation_id)

    add_failed_import_operation_responses(
        strict_httpx,
        operation_id,
        result_image_uuid,
    )

    return strict_httpx
