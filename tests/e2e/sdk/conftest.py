from random import choices
from uuid import UUID

import pytest

from contree_sdk import Contree, ContreeSync
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.sdk.objects.session._async import ContreeSession
from contree_sdk.sdk.objects.session._sync import ContreeSessionSync


@pytest.fixture
async def image(contree: Contree) -> ContreeImage:
    images = await contree.images()
    return choices(images)[0]


@pytest.fixture
def image_s(contree_s: ContreeSync) -> ContreeImageSync:
    images = contree_s.images()
    return choices(images)[0]


@pytest.fixture
def image_uuid(image: ContreeImage) -> UUID:
    assert image.uuid is not None  # noqa: S101
    return image.uuid


@pytest.fixture
async def image_tag(contree: Contree) -> str:
    images = await contree.images()
    for image in images:
        if not image.tag:
            continue
        return image.tag
    raise ValueError("Image tag not found")


@pytest.fixture
def session(image: ContreeImage) -> ContreeSession:
    return image.session()


@pytest.fixture
def session_s(image_s: ContreeImageSync) -> ContreeSessionSync:
    return image_s.session()
