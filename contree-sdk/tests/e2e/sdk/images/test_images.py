from uuid import UUID

import pytest

from contree_sdk import Contree, ContreeSync
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync


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


def test_pull_image_by_uuid_s(contree_s: ContreeSync):
    image = contree_s.images.pull("0bd59a5d-9f0d-4fab-9376-001ec247cd78")
    assert isinstance(image.uuid, UUID)
    assert isinstance(image, ContreeImageSync)


def test_pull_image_by_tag_s(contree_s: ContreeSync):
    image = contree_s.images.pull("python:3.13")
    assert isinstance(image.uuid, UUID)
    assert isinstance(image, ContreeImageSync)
    assert image.tag == "python:3.13"
