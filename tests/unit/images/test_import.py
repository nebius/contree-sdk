from pytest_httpx import HTTPXMock

from contree_sdk import ContreeSync
from tests.e2e.sdk.images.test_images import test_import_not_real_image_s as _test_import_not_real_image_s
from tests.e2e.sdk.images.test_images import test_import_public_image_s as _test_import_public_image_s


def test_import_public_image_s(fake_contree_s: ContreeSync, api_fake_import: HTTPXMock):
    _test_import_public_image_s(fake_contree_s)


def test_pull_import_not_real_image_s(fake_contree_s: ContreeSync, api_fake_import_failed: HTTPXMock):
    _test_import_not_real_image_s(fake_contree_s)
