from pytest_httpx import HTTPXMock

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from tests.e2e.sdk.images.test_inspect import test_download_file as _test_download_file
from tests.e2e.sdk.images.test_inspect import test_download_file_s as _test_download_file_s
from tests.e2e.sdk.images.test_inspect import test_image_ls as _test_image_ls
from tests.e2e.sdk.images.test_inspect import test_image_ls_s as _test_image_ls_s
from tests.e2e.sdk.images.test_inspect import test_read_file as _test_read_file
from tests.e2e.sdk.images.test_inspect import test_read_file_s as _test_read_file_s


async def test_image_ls(api_fake_inspect_ls: HTTPXMock, fake_image: ContreeImage):
    await _test_image_ls(fake_image)


def test_image_ls_s(api_fake_inspect_ls: HTTPXMock, fake_image_s: ContreeImageSync):
    _test_image_ls_s(fake_image_s)


async def test_download_file(api_fake_inspect_download: HTTPXMock, fake_image: ContreeImage, random_data: bytes):
    await _test_download_file(fake_image, random_data)


def test_download_file_s(api_fake_inspect_download: HTTPXMock, fake_image_s: ContreeImageSync, random_data: bytes):
    _test_download_file_s(fake_image_s, random_data)


async def test_read_file(api_fake_inspect_download: HTTPXMock, fake_image: ContreeImage, random_data: bytes):
    await _test_read_file(fake_image, random_data)


def test_read_file_s(api_fake_inspect_download: HTTPXMock, fake_image_s: ContreeImageSync, random_data: bytes):
    _test_read_file_s(fake_image_s, random_data)
