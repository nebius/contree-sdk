from collections.abc import AsyncIterator, Iterator

import pytest
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk import Contree, ContreeSync
from tests.unit.fixtures.files import file_sha256, file_uuid
from tests.unit.fixtures.images import fake_image, fake_image_s, image_tag, image_uuid
from tests.unit.fixtures.imports import result_image_uuid
from tests.unit.fixtures.operations import operation_id


__all__ = [
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
async def fake_api() -> AsyncIterator[ContreeAsyncClient]:
    """A `contree_client.testing.ContreeAsyncClient` double, unmocked by default."""
    async with ContreeAsyncClient() as api:
        yield api


@pytest.fixture
def fake_api_s() -> Iterator[ContreeClient]:
    """A `contree_client.testing.ContreeClient` double, unmocked by default."""
    with ContreeClient() as api:
        yield api


@pytest.fixture
def fake_contree(fake_api: ContreeAsyncClient) -> Contree:
    return Contree(fake_api)


@pytest.fixture
def fake_contree_s(fake_api_s: ContreeClient) -> ContreeSync:
    return ContreeSync(fake_api_s)
