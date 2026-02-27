from uuid import UUID

import pytest
from pytest_httpx import HTTPXMock

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from tests.e2e.sdk.images.test_tagging import test_tag_image as _test_tag_image
from tests.e2e.sdk.images.test_tagging import test_tag_image_s as _test_tag_image_s
from tests.e2e.sdk.images.test_tagging import test_untag_image as _test_untag_image
from tests.e2e.sdk.images.test_tagging import test_untag_image_s as _test_untag_image_s
from tests.unit.fixtures.images import add_tag_responses, add_untag_responses


@pytest.fixture
def api_fake_tag(image_uuid: UUID, image_tag: str, api_fake_images: HTTPXMock) -> HTTPXMock:
    add_tag_responses(api_fake_images, image_uuid, count=2)
    return api_fake_images


@pytest.fixture
def api_fake_untag(image_uuid: UUID, image_tag: str, api_fake_images: HTTPXMock) -> HTTPXMock:
    add_tag_responses(api_fake_images, image_uuid, count=1)
    add_untag_responses(api_fake_images, image_uuid, count=1)
    add_tag_responses(api_fake_images, image_uuid, count=1)
    return api_fake_images


async def test_tag_image(fake_image: ContreeImage, api_fake_tag: HTTPXMock):
    await _test_tag_image(fake_image)


def test_tag_image_s(fake_image_s: ContreeImageSync, api_fake_tag: HTTPXMock):
    _test_tag_image_s(fake_image_s)


async def test_untag_image(fake_image: ContreeImage, api_fake_untag: HTTPXMock):
    await _test_untag_image(fake_image)


def test_untag_image_s(fake_image_s: ContreeImageSync, api_fake_untag: HTTPXMock):
    _test_untag_image_s(fake_image_s)
