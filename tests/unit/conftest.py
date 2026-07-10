from uuid import uuid4

import pytest
from pytest_httpx import HTTPXMock

from contree_sdk import Contree, ContreeSync
from contree_sdk.auth import IAMAuth
from contree_sdk.config import ContreeConfig
from tests.unit.fixtures.auth import api_fake_whoami, token_uuid
from tests.unit.fixtures.files import add_file_responses, api_fake_upload, file_sha256, file_uuid
from tests.unit.fixtures.images import (
    api_fake_forbidden,
    api_fake_images,
    fake_image,
    fake_image_s,
    image_tag,
    image_uuid,
)
from tests.unit.fixtures.imports import (
    api_fake_import,
    api_fake_import_cancel,
    api_fake_import_failed,
    api_fake_import_slow,
)
from tests.unit.fixtures.operations import api_fake_streamed_run, operation_id
from tests.unit.fixtures.runs import (
    api_fake_apply_files,
    api_fake_popen,
    api_fake_popen_communicate,
    api_fake_popen_env,
    api_fake_popen_error,
    api_fake_popen_shell,
    api_fake_popen_stdin,
    api_fake_run,
    api_fake_run_base,
    api_fake_run_deferred,
    api_fake_run_preserve_env,
    api_fake_run_truncated,
    api_fake_run_with_files,
    api_fake_run_without_preserve_env,
    api_fake_session_multiple_runs,
    api_fake_thread_pool,
    process_state,
    resource_usage,
    result_image_uuid,
)


__all__ = [
    "add_file_responses",
    "api_fake_apply_files",
    "api_fake_forbidden",
    "api_fake_images",
    "api_fake_import",
    "api_fake_import_cancel",
    "api_fake_import_failed",
    "api_fake_import_slow",
    "api_fake_popen",
    "api_fake_popen_communicate",
    "api_fake_popen_env",
    "api_fake_popen_error",
    "api_fake_popen_shell",
    "api_fake_popen_stdin",
    "api_fake_run",
    "api_fake_run_base",
    "api_fake_run_deferred",
    "api_fake_run_preserve_env",
    "api_fake_run_truncated",
    "api_fake_run_with_files",
    "api_fake_run_without_preserve_env",
    "api_fake_session_multiple_runs",
    "api_fake_streamed_run",
    "api_fake_thread_pool",
    "api_fake_upload",
    "api_fake_whoami",
    "fake_contree",
    "fake_contree_config",
    "fake_contree_s",
    "fake_image",
    "fake_image_s",
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
    "token_uuid",
]


@pytest.fixture
def fake_token() -> str:
    return "fake-token"


@pytest.fixture
def fake_project_id() -> str:
    return "fake-project_id-" + uuid4().hex[:4]


@pytest.fixture
def fake_contree_config(fake_token: str, fake_project_id: str) -> ContreeConfig:
    return ContreeConfig(
        auth=IAMAuth(token=fake_token, base_url="https://fake.contree.endpoint", project_id=fake_project_id)
    )


@pytest.fixture
def fake_contree(fake_contree_config: ContreeConfig) -> Contree:
    return Contree(config=fake_contree_config)


@pytest.fixture
def fake_contree_s(fake_contree_config: ContreeConfig) -> ContreeSync:
    return ContreeSync(config=fake_contree_config)


@pytest.fixture
def strict_httpx(httpx_mock: HTTPXMock, fake_token: str, fake_project_id: str) -> HTTPXMock:
    httpx_mock.reset()
    httpx_mock.strict_responses = True

    original_add_response = httpx_mock.add_response

    def add_response_with_auth(*args, **kwargs):

        kwargs.setdefault("match_headers", {})
        kwargs["match_headers"].setdefault("Authorization", f"Bearer {fake_token}")
        kwargs["match_headers"].setdefault("Project", f"{fake_project_id}")
        return original_add_response(*args, **kwargs)

    httpx_mock.add_response = add_response_with_auth
    return httpx_mock
