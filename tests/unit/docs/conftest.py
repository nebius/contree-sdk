from pathlib import Path, PurePosixPath
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from _pytest.monkeypatch import MonkeyPatch
from pytest_httpx import HTTPXMock
from tests.unit.conftest import fake_contree_config, fake_contree_s, fake_project_id, fake_token, strict_httpx
from tests.unit.fixtures.files import add_file_responses, api_fake_upload, file_sha256, file_uuid
from tests.unit.fixtures.images import add_inspect_by_tag_response, api_fake_images, fake_image_s, image_tag, image_uuid
from tests.unit.fixtures.imports import add_import_operation_responses
from tests.unit.fixtures.operations import (
    add_base_responses,
    add_inspect_list_download_responses,
    add_operation_responses,
    operation_id,
)
from tests.unit.fixtures.runs import (
    api_fake_popen_communicate,
    api_fake_popen_shell,
    api_fake_run,
    api_fake_run_base,
    api_fake_session_multiple_runs,
    process_state,
    resource_usage,
    result_image_uuid,
)
from tests.unit.fixtures.utils import r, url

from contree_sdk._internals.models.instance import ProcessResources, ProcessState
from contree_sdk.sdk.managers.files._async import FilesManager
from contree_sdk.sdk.managers.files._base import _FilesBaseManager
from contree_sdk.sdk.objects.image import ContreeImageSync
from contree_sdk.sdk.objects.session import ContreeSessionSync


__all__ = [
    "api_fake_images",
    "api_fake_popen_communicate",
    "api_fake_popen_shell",
    "api_fake_quick_start",
    "api_fake_run",
    "api_fake_run_base",
    "api_fake_session_multiple_runs",
    "api_fake_stable_uuid",
    "api_fake_upload",
    "docs_file_upload",
    "fake_contree_config",
    "fake_contree_s",
    "fake_image_s",
    "fake_project_id",
    "fake_token",
    "file_sha256",
    "file_uuid",
    "image_tag",
    "image_uuid",
    "operation_id",
    "process_state",
    "resource_usage",
    "result_image_uuid",
    "session",
    "strict_httpx",
]


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool:
    return "_tmp" in str(collection_path)


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
    from tests.unit.fixtures.runs import add_inspect_by_uuid_response

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

    add_inspect_by_uuid_response(strict_httpx, result_image_uuid)

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
def session(fake_image_s: ContreeImageSync) -> ContreeSessionSync:
    return fake_image_s.session()


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

    from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase

    original_download = _ImageLikeBase._download

    async def patched_download(
        self: _ImageLikeBase, image_path: str | PurePosixPath, local_path: str | Path | None = None
    ):
        if local_path is not None:
            path = Path(local_path)
            if path.is_absolute():
                relative = path.relative_to(path.anchor)
                redirected_path = tmp_path / relative
                if redirected_path.is_dir() or str(local_path).endswith("/"):
                    redirected_path /= Path(image_path).name
                local_path = redirected_path
        return await original_download(self, image_path, local_path)

    with (
        patch.object(_FilesBaseManager, "_upload_file", patched_upload),
        patch.object(FilesManager, "upload", patched_upload),
        patch.object(_ImageLikeBase, "_download", patched_download),
    ):
        yield tmp_path


@pytest.fixture
def api_fake_quick_start(
    image_uuid: UUID,
    file_uuid: str,
    file_sha256: str,
    process_state: ProcessState,
    resource_usage: ProcessResources,
    api_fake_session_multiple_runs: HTTPXMock,
    docs_file_upload: Path,
) -> HTTPXMock:
    (docs_file_upload / "local/files").mkdir(parents=True, exist_ok=True)
    (docs_file_upload / "local/files/app.sh").write_text("#!/bin/sh")
    (docs_file_upload / "local/files/data_ver1.csv").write_text("data")
    (docs_file_upload / "local/files/app").write_text("app")
    (docs_file_upload / "local/files/downloaded").mkdir(parents=True, exist_ok=True)
    (docs_file_upload / "local/logs").mkdir(parents=True, exist_ok=True)

    ubuntu_uuid = uuid4()
    busybox_uuid = uuid4()

    add_file_responses(api_fake_session_multiple_runs, file_uuid, file_sha256)
    add_file_responses(api_fake_session_multiple_runs, file_uuid, file_sha256)

    api_fake_session_multiple_runs.add_response(
        method="GET", url=r(".*/images\\?.*"), json={"images": []}, is_optional=True
    )

    add_inspect_by_tag_response(api_fake_session_multiple_runs, "ubuntu:latest", ubuntu_uuid)

    api_fake_session_multiple_runs.add_response(
        method="GET",
        url=url("/inspect/", params={"tag": "busybox:latest"}),
        status_code=404,
        json={"error": "Image not found", "status": 404},
        is_optional=True,
    )

    import_op_id = str(uuid4())
    api_fake_session_multiple_runs.add_response(
        method="POST", url=r(".*/images/import"), json={"uuid": import_op_id}, is_optional=True
    )
    add_base_responses(api_fake_session_multiple_runs, import_op_id)
    add_import_operation_responses(api_fake_session_multiple_runs, import_op_id, busybox_uuid)

    add_inspect_list_download_responses(api_fake_session_multiple_runs)

    return api_fake_session_multiple_runs


@pytest.fixture(autouse=True)
def set_contree_base_url_env(monkeypatch: MonkeyPatch, fake_project_id: str):
    monkeypatch.setenv("CONTREE_BASE_URL", "https://fake.contree.endpoint")
    monkeypatch.setenv("NEBIUS_PROJECT_ID", fake_project_id)
