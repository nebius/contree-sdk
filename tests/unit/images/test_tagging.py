from uuid import UUID

import pytest

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from tests.e2e.sdk.images.test_tagging import test_tag_image as _test_tag_image
from tests.e2e.sdk.images.test_tagging import test_tag_image_s as _test_tag_image_s
from tests.e2e.sdk.images.test_tagging import test_untag_image as _test_untag_image
from tests.e2e.sdk.images.test_tagging import test_untag_image_s as _test_untag_image_s
from tests.unit.fixtures.images import queue_tag, queue_untag


@pytest.fixture
def api_fake_tag(fake_api, fake_api_s, image_uuid: UUID, image_tag: str):
    queue_tag(fake_api, image_uuid, image_tag, count=2)
    queue_tag(fake_api_s, image_uuid, image_tag, count=2)
    return fake_api_s


@pytest.fixture
def api_fake_untag(fake_api, fake_api_s, image_uuid: UUID, image_tag: str):
    for api in (fake_api, fake_api_s):
        queue_tag(api, image_uuid, image_tag, count=1)
        queue_untag(api, count=1)
        queue_tag(api, image_uuid, image_tag, count=1)
    return fake_api_s


async def test_tag_image(fake_image: ContreeImage, api_fake_tag):
    await _test_tag_image(fake_image)


def test_tag_image_s(fake_image_s: ContreeImageSync, api_fake_tag):
    _test_tag_image_s(fake_image_s)


async def test_untag_image(fake_image: ContreeImage, api_fake_untag):
    await _test_untag_image(fake_image)


def test_untag_image_s(fake_image_s: ContreeImageSync, api_fake_untag):
    _test_untag_image_s(fake_image_s)
