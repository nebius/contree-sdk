from pytest_httpx import HTTPXMock

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from tests.e2e.sdk.images.test_inspect import test_image_ls as _test_image_ls
from tests.e2e.sdk.images.test_inspect import test_image_ls_s as _test_image_ls_s


async def test_image_ls(api_fake_inspect_ls: HTTPXMock, fake_image: ContreeImage):
    await _test_image_ls(fake_image)


def test_image_ls_s(api_fake_inspect_ls: HTTPXMock, fake_image_s: ContreeImageSync):
    _test_image_ls_s(fake_image_s)
