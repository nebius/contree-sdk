import pytest
from pytest_httpx import HTTPXMock

from contree_sdk import Contree, ContreeSync
from contree_sdk.config import ContreeConfig
from tests.unit.fixtures.files import add_file_responses, file_sha256, file_uuid
from tests.unit.fixtures.images import api_fake_images, fake_image, fake_image_s, image_tag, image_uuid
from tests.unit.fixtures.imports import api_fake_import, api_fake_import_failed
from tests.unit.fixtures.operations import operation_id
from tests.unit.fixtures.runs import (
    api_fake_run,
    api_fake_run_base,
    api_fake_run_with_files,
    process_state,
    resource_usage,
    result_image_uuid,
)


__all__ = [
    "add_file_responses",
    "api_fake_images",
    "api_fake_import",
    "api_fake_import_failed",
    "api_fake_run",
    "api_fake_run_base",
    "api_fake_run_with_files",
    "fake_contree",
    "fake_contree_config",
    "fake_contree_s",
    "fake_image",
    "fake_image_s",
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


@pytest.fixture()
def fake_contree_config() -> ContreeConfig:
    return ContreeConfig(token="fake-token", base_url="https://fake.contree.endpoint")


@pytest.fixture()
def fake_contree(fake_contree_config: ContreeConfig) -> Contree:
    return Contree(config=fake_contree_config)


@pytest.fixture()
def fake_contree_s(fake_contree_config: ContreeConfig) -> ContreeSync:
    return ContreeSync(config=fake_contree_config)


@pytest.fixture()
def strict_httpx(httpx_mock: HTTPXMock) -> HTTPXMock:
    httpx_mock.reset()
    httpx_mock.strict_responses = True
    return httpx_mock
