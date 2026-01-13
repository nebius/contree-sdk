from pathlib import Path
from unittest.mock import patch

import pytest
from pytest_httpx import HTTPXMock
from tests.unit.conftest import fake_token, strict_httpx
from tests.unit.fixtures.files import api_fake_upload, file_sha256, file_uuid
from tests.unit.fixtures.images import api_fake_images, image_tag, image_uuid
from tests.unit.fixtures.operations import operation_id
from tests.unit.fixtures.runs import api_fake_session_multiple_runs, process_state, resource_usage, result_image_uuid

from contree_sdk.sdk.managers.files._async import FilesManager
from contree_sdk.sdk.managers.files._base import _FilesBaseManager


__all__ = [
    "api_fake_images",
    "api_fake_session_multiple_runs",
    "api_fake_upload",
    "docs_file_upload",
    "fake_token",
    "file_sha256",
    "file_uuid",
    "image_tag",
    "image_uuid",
    "operation_id",
    "process_state",
    "resource_usage",
    "result_image_uuid",
    "strict_httpx",
]


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
