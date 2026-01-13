from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest
from pytest_httpx import HTTPXMock
from tests.unit.conftest import fake_contree_config, fake_contree_s, fake_token, strict_httpx
from tests.unit.fixtures.files import api_fake_upload, file_sha256, file_uuid
from tests.unit.fixtures.images import api_fake_images, fake_image_s, image_tag, image_uuid
from tests.unit.fixtures.operations import operation_id
from tests.unit.fixtures.runs import (
    api_fake_run,
    api_fake_run_base,
    api_fake_session_multiple_runs,
    process_state,
    resource_usage,
    result_image_uuid,
)

from contree_sdk._internals.models.instance import ProcessResources, ProcessState
from contree_sdk.sdk.managers.files._async import FilesManager
from contree_sdk.sdk.managers.files._base import _FilesBaseManager
from contree_sdk.sdk.objects.image import ContreeImageSync


__all__ = [
    "api_fake_images",
    "api_fake_run",
    "api_fake_run_base",
    "api_fake_session_multiple_runs",
    "api_fake_stable_uuid",
    "api_fake_upload",
    "docs_file_upload",
    "fake_contree_config",
    "fake_contree_s",
    "fake_image_s",
    "fake_token",
    "file_sha256",
    "file_uuid",
    "image",
    "image_tag",
    "image_uuid",
    "operation_id",
    "process_state",
    "resource_usage",
    "result_image_uuid",
    "strict_httpx",
]


@pytest.fixture
def api_fake_stable_uuid(
    image_uuid: UUID,
    result_image_uuid: UUID,
    file_uuid: str,
    file_sha256: str,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    strict_httpx: HTTPXMock,
) -> HTTPXMock:
    from uuid import uuid4

    from tests.unit.fixtures.files import add_file_responses
    from tests.unit.fixtures.operations import add_operation_responses
    from tests.unit.fixtures.utils import r

    add_file_responses(strict_httpx, file_uuid, file_sha256)

    strict_httpx.add_response(
        method="DELETE",
        url=r(".*/operations/.*"),
        json={},
        is_optional=True,
    )

    op_id1 = str(uuid4())
    strict_httpx.add_response(
        method="POST",
        url=r(".*/instances"),
        json={"uuid": op_id1},
        is_optional=True,
    )

    strict_httpx.add_response(
        method="GET",
        url=r(f".*/inspect/{result_image_uuid}$"),
        json={"uuid": str(result_image_uuid), "tag": None, "created_at": "2024-01-01T12:00:00+00:00"},
        is_optional=True,
    )

    add_operation_responses(
        strict_httpx,
        op_id1,
        image_uuid,
        result_image_uuid,
        process_state,
        resource_usage,
        "",
        "",
    )

    op_id2 = str(uuid4())
    strict_httpx.add_response(
        method="POST",
        url=r(".*/instances"),
        json={"uuid": op_id2},
        is_optional=True,
    )

    add_operation_responses(
        strict_httpx,
        op_id2,
        result_image_uuid,
        result_image_uuid,
        process_state,
        resource_usage,
        "",
        "",
    )

    return strict_httpx


@pytest.fixture
def image(fake_image_s: ContreeImageSync) -> ContreeImageSync:
    return fake_image_s


@pytest.fixture
def docs_file_upload(tmp_path: Path, api_fake_upload: HTTPXMock):
    file_path = tmp_path / "some/local/file.txt"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("test file content")

    original_upload = _FilesBaseManager._upload_file

    async def patched_upload(self: _FilesBaseManager, local_path: str | Path):
        path = Path(local_path)
        relative = path.relative_to(path.anchor) if path.is_absolute() else path
        prefixed_path = tmp_path / relative
        return await original_upload(self, prefixed_path)

    with (
        patch.object(_FilesBaseManager, "_upload_file", patched_upload),
        patch.object(FilesManager, "upload", patched_upload),
    ):
        yield tmp_path
