from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from contree_client.models import OperationResponse, OperationStatus


def queue_import(
    api: Any,
    *,
    operation_id: str | None = None,
    result_image_uuid: UUID | None = None,
    status: OperationStatus = OperationStatus.SUCCESS,
    error: str | None = None,
) -> str:
    operation_id = operation_id or str(uuid4())
    api.mock("import_image", operation_id)
    api.mock(
        "wait_operation",
        OperationResponse(
            uuid=operation_id,
            status=status,
            result_image_uuid=str(result_image_uuid) if result_image_uuid is not None else None,
            error=error,
        ),
    )
    return operation_id


@pytest.fixture
def result_image_uuid() -> UUID:
    return uuid4()


@pytest.fixture
def api_fake_import(fake_api: Any, fake_api_s: Any, result_image_uuid: UUID) -> Any:
    queue_import(fake_api, result_image_uuid=result_image_uuid)
    queue_import(fake_api_s, result_image_uuid=result_image_uuid)
    return fake_api_s


@pytest.fixture
def api_fake_import_failed(fake_api: Any, fake_api_s: Any, result_image_uuid: UUID) -> Any:
    queue_import(fake_api, status=OperationStatus.FAILED, error="Import failed")
    queue_import(fake_api_s, status=OperationStatus.FAILED, error="Import failed")
    return fake_api_s


@pytest.fixture
def api_fake_import_cancel(fake_api: Any, fake_api_s: Any, result_image_uuid: UUID) -> Any:
    queue_import(fake_api, status=OperationStatus.CANCELLED)
    queue_import(fake_api_s, status=OperationStatus.CANCELLED)
    return fake_api_s


@pytest.fixture
def api_fake_import_slow(fake_api: Any, fake_api_s: Any, result_image_uuid: UUID) -> Any:
    queue_import(fake_api, status=OperationStatus.CANCELLED)
    queue_import(fake_api_s, status=OperationStatus.CANCELLED)
    return fake_api_s
