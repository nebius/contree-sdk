import pytest
from pytest_httpx import HTTPXMock

from contree_sdk import Contree, ContreeSync
from tests.e2e.sdk.images.test_images import test_get_all_images as _test_get_all_images
from tests.e2e.sdk.images.test_images import test_pull_image_by_tag_s as _test_pull_image_by_tag_s
from tests.e2e.sdk.images.test_images import test_pull_image_by_uuid_s as _test_pull_image_by_uuid_s
from tests.e2e.sdk.images.test_images import test_pull_nonexistent_tag_image_s as _test_pull_nonexistent_tag_image_s
from tests.e2e.sdk.images.test_images import test_pull_nonexistent_uuid_image_s as _test_pull_nonexistent_uuid_image_s


@pytest.mark.parametrize("client_type", ["async", "sync"])
async def test_get_all_images(
    client_type, fake_contree: Contree, fake_contree_s: ContreeSync, api_fake_images: HTTPXMock
):
    await _test_get_all_images(client_type, fake_contree, fake_contree_s)


def test_pull_image_by_uuid_s(fake_contree_s: ContreeSync, image_uuid, api_fake_images: HTTPXMock):
    _test_pull_image_by_uuid_s(fake_contree_s, image_uuid)


def test_pull_image_by_tag_s(fake_contree_s: ContreeSync, image_tag, api_fake_images: HTTPXMock):
    _test_pull_image_by_tag_s(fake_contree_s, image_tag)


def test_pull_nonexistent_uuid_image_s(fake_contree_s: ContreeSync, api_fake_images: HTTPXMock):
    _test_pull_nonexistent_uuid_image_s(fake_contree_s)


def test_pull_nonexistent_tag_image_s(fake_contree_s: ContreeSync, api_fake_images: HTTPXMock):
    _test_pull_nonexistent_tag_image_s(fake_contree_s)
