import pytest
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk import Contree, ContreeSync
from tests.unit.fixtures.files import api_fake_upload, file_sha256, file_uuid
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
    result_image_uuid,
)
from tests.unit.fixtures.operations import operation_id
from tests.unit.fixtures.runs import (
    api_fake_apply_files,
    api_fake_popen,
    api_fake_popen_communicate,
    api_fake_popen_env,
    api_fake_popen_error,
    api_fake_popen_shell,
    api_fake_popen_stdin,
    api_fake_run,
    api_fake_run_deferred,
    api_fake_run_preserve_env,
    api_fake_run_truncated,
    api_fake_run_with_files,
    api_fake_run_without_preserve_env,
    api_fake_session_multiple_runs,
    api_fake_slow_run,
    api_fake_thread_pool,
)


__all__ = [
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
    "api_fake_run_deferred",
    "api_fake_run_preserve_env",
    "api_fake_run_truncated",
    "api_fake_run_with_files",
    "api_fake_run_without_preserve_env",
    "api_fake_session_multiple_runs",
    "api_fake_slow_run",
    "api_fake_thread_pool",
    "api_fake_upload",
    "fake_api",
    "fake_api_s",
    "fake_contree",
    "fake_contree_s",
    "fake_image",
    "fake_image_s",
    "file_sha256",
    "file_uuid",
    "image_tag",
    "image_uuid",
    "operation_id",
    "result_image_uuid",
]


@pytest.fixture
def fake_api() -> ContreeAsyncClient:
    """A `contree_client.testing.ContreeAsyncClient` double, unmocked by default."""
    return ContreeAsyncClient()


@pytest.fixture
def fake_api_s() -> ContreeClient:
    """A `contree_client.testing.ContreeClient` double, unmocked by default."""
    return ContreeClient()


@pytest.fixture
def fake_contree(fake_api: ContreeAsyncClient) -> Contree:
    return Contree(fake_api)


@pytest.fixture
def fake_contree_s(fake_api_s: ContreeClient) -> ContreeSync:
    return ContreeSync(fake_api_s)
