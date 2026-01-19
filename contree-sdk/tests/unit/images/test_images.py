from uuid import uuid4

import pytest
from pytest_httpx import HTTPXMock

from contree_sdk import Contree, ContreeSync
from contree_sdk.utils.models.image import ImageKind
from tests.e2e.sdk.images.test_images import test_get_all_images as _test_get_all_images
from tests.e2e.sdk.images.test_images import test_get_images_with_parameters_s as _test_get_images_with_parameters_s
from tests.e2e.sdk.images.test_images import test_iter_images as _test_iter_images
from tests.e2e.sdk.images.test_images import test_iter_images_s as _test_iter_images_s
from tests.e2e.sdk.images.test_images import test_pull_image_by_tag_s as _test_pull_image_by_tag_s
from tests.e2e.sdk.images.test_images import test_pull_image_by_uuid_s as _test_pull_image_by_uuid_s
from tests.e2e.sdk.images.test_images import test_pull_nonexistent_tag_image_s as _test_pull_nonexistent_tag_image_s
from tests.e2e.sdk.images.test_images import test_pull_nonexistent_uuid_image_s as _test_pull_nonexistent_uuid_image_s
from tests.unit.fixtures.utils import r


@pytest.fixture
def api_fake_images_with_params(strict_httpx: HTTPXMock) -> HTTPXMock:
    image1 = {"uuid": str(uuid4()), "tag": "test-image-1:latest", "created_at": "2024-01-01T12:00:00+00:00"}
    image2 = {"uuid": str(uuid4()), "tag": "test-image-2:latest", "created_at": "2024-01-01T12:00:00+00:00"}

    strict_httpx.add_response(
        method="GET",
        url=r(
            f".*/images\\?kind={ImageKind.IMPORTED}&limit=2&offset=0&tagged=1&since=2025-01-01T00%3A00%3A00&until=.*"
        ),
        json={"images": [image1, image2]},
        is_optional=True,
    )

    return strict_httpx


@pytest.fixture
def api_fake_images_with_404(api_fake_images: HTTPXMock) -> HTTPXMock:
    api_fake_images.add_response(
        method="GET",
        url=r(".*/inspect/.*"),
        json={"error": "Image not found", "status": 404},
        is_optional=True,
        status_code=404,
    )
    api_fake_images.add_response(
        method="GET",
        url=r(r".*/inspect\?tag=.*"),
        json={"error": "Image not found", "status": 404},
        is_optional=True,
        status_code=404,
    )
    return api_fake_images


@pytest.mark.parametrize("client_type", ["async", "sync"])
async def test_get_all_images(
    client_type, fake_contree: Contree, fake_contree_s: ContreeSync, api_fake_images: HTTPXMock
):
    await _test_get_all_images(client_type, fake_contree, fake_contree_s)


def test_pull_image_by_uuid_s(fake_contree_s: ContreeSync, image_uuid, api_fake_images: HTTPXMock):
    _test_pull_image_by_uuid_s(fake_contree_s, image_uuid)


def test_pull_image_by_tag_s(fake_contree_s: ContreeSync, image_tag, api_fake_images: HTTPXMock):
    _test_pull_image_by_tag_s(fake_contree_s, image_tag)


def test_pull_nonexistent_uuid_image_s(fake_contree_s: ContreeSync, api_fake_images_with_404: HTTPXMock):
    _test_pull_nonexistent_uuid_image_s(fake_contree_s)


def test_pull_nonexistent_tag_image_s(fake_contree_s: ContreeSync, api_fake_images_with_404: HTTPXMock):
    _test_pull_nonexistent_tag_image_s(fake_contree_s)


async def test_iter_images(fake_contree: Contree, api_fake_images: HTTPXMock):
    await _test_iter_images(fake_contree)


def test_iter_images_s(fake_contree_s: ContreeSync, api_fake_images: HTTPXMock):
    _test_iter_images_s(fake_contree_s)


def test_get_images_with_parameters_s(fake_contree_s: ContreeSync, api_fake_images_with_params: HTTPXMock):
    _test_get_images_with_parameters_s(fake_contree_s)
