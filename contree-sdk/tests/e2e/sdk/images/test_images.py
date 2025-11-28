from uuid import UUID

import pytest

from contree_sdk import Contree, ContreeSync
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.sdk.objects.image_like.state import ImageState


@pytest.mark.parametrize("client_type", ["async", "sync"])
async def test_get_all_images(client_type, contree: Contree, contree_s: ContreeSync):
    if client_type == "async":
        images = await contree.images()
    else:
        images = contree_s.images()
    assert len(images) > 0
    was_str_tag = False
    for image in images:
        assert isinstance(image.uuid, UUID)
        if isinstance(image.tag, str):
            was_str_tag = True
        if client_type == "async":
            assert isinstance(image, ContreeImage)
        else:
            assert isinstance(image, ContreeImageSync)
        if was_str_tag:
            break
    assert was_str_tag


@pytest.fixture
async def image_uuid(contree: Contree) -> UUID:
    images = await contree.images()
    for image in images:
        return image.uuid
    raise ValueError("Image uuid not found")


@pytest.fixture
async def image_tag(contree: Contree) -> str:
    images = await contree.images()
    for image in images:
        if not image.tag:
            continue
        return image.tag
    raise ValueError("Image tag not found")


def test_pull_image_by_uuid_s(contree_s: ContreeSync, image_uuid):
    image = contree_s.images.pull(str(image_uuid))
    assert isinstance(image.uuid, UUID)
    assert isinstance(image, ContreeImageSync)
    assert image.uuid == image_uuid


def test_pull_image_by_tag_s(contree_s: ContreeSync, image_tag):
    image = contree_s.images.pull(image_tag)
    assert isinstance(image.uuid, UUID)
    assert isinstance(image, ContreeImageSync)
    assert image.tag == image_tag


def test_import_public_image_s(contree_s: ContreeSync):
    url = "docker://ghcr.io/linuxserver/code-server:latest"
    image = contree_s.images.pull(url)
    assert isinstance(image, ContreeImageSync)
    assert isinstance(image.uuid, UUID)
    assert image.state == ImageState.PULLED
    assert "code-server:latest" in image.tag


# todo make proper exception for this
# def test_pull_nonexistent_uuid_image(contree_s: ContreeSync):
#     with pytest.raises(ContreeImageNotFound):
#         contree_s.images.pull(uuid4()) # noqa: ERA001


# todo add test for failed import
# todo add test for private import
