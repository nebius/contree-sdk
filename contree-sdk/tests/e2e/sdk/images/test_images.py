from uuid import UUID

import pytest


@pytest.fixture(params=["async", "sync"])
async def images(request, contree, contree_s):
    if request.param == "async":
        return await contree.images()
    return contree_s.images()


async def test_get_all_images(images):
    assert len(images) > 0
    for image in images:
        UUID(image.uuid)
        assert isinstance(image.tag, str)
        break
