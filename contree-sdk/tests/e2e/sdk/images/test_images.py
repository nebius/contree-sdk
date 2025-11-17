from uuid import UUID

import pytest

from contree_sdk import Contree, ContreeSync


@pytest.fixture(params=["async", "sync"])
async def images(request, contree: Contree, contree_s: ContreeSync):
    if request.param == "async":
        images = await contree.images()
    else:
        images = contree_s.images()
    return images


async def test_get_all_images(images):
    assert len(images) > 0
    for image in images:
        UUID(image.uuid)
        assert isinstance(image.tag, str)
        break
