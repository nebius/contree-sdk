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
