from uuid import uuid4

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync


def _test_tag() -> str:
    return f"test-e2e-{uuid4().hex[:8]}"


async def test_tag_image(image: ContreeImage):
    original_tag = image.tag
    test_tag = _test_tag()
    try:
        tagged = await image.tag_as(test_tag)
        assert isinstance(tagged, ContreeImage)
        assert tagged.tag == test_tag
    finally:
        await image.tag_as(original_tag)


async def test_untag_image(image: ContreeImage):
    original_tag = image.tag
    test_tag = _test_tag()
    await image.tag_as(test_tag)
    try:
        untagged = await image.untag()
        assert isinstance(untagged, ContreeImage)
        assert untagged.tag is None
    finally:
        if original_tag:
            await image.tag_as(original_tag)


def test_tag_image_s(image_s: ContreeImageSync):
    original_tag = image_s.tag
    test_tag = _test_tag()
    try:
        tagged = image_s.tag_as(test_tag)
        assert isinstance(tagged, ContreeImageSync)
        assert tagged.tag == test_tag
    finally:
        image_s.tag_as(original_tag)


def test_untag_image_s(image_s: ContreeImageSync):
    original_tag = image_s.tag
    test_tag = _test_tag()
    image_s.tag_as(test_tag)
    try:
        untagged = image_s.untag()
        assert isinstance(untagged, ContreeImageSync)
        assert untagged.tag is None
    finally:
        if original_tag:
            image_s.tag_as(original_tag)
