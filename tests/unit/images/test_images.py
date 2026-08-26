import pytest

from contree_sdk import Contree, ContreeSync
from tests.e2e.sdk.images.test_images import test_get_all_images as _test_get_all_images
from tests.e2e.sdk.images.test_images import test_iter_images as _test_iter_images
from tests.e2e.sdk.images.test_images import test_iter_images_s as _test_iter_images_s
from tests.e2e.sdk.images.test_images import test_oci_image_by_tag_s as _test_oci_image_by_tag_s
from tests.e2e.sdk.images.test_images import test_oci_nonexistent_uuid_s as _test_oci_nonexistent_uuid_s
from tests.e2e.sdk.images.test_images import test_oci_public_image_s as _test_oci_public_image_s
from tests.e2e.sdk.images.test_images import test_pull_image_by_tag_s as _test_pull_image_by_tag_s
from tests.e2e.sdk.images.test_images import test_pull_image_by_uuid_s as _test_pull_image_by_uuid_s
from tests.e2e.sdk.images.test_images import test_pull_nonexistent_tag_image_s as _test_pull_nonexistent_tag_image_s
from tests.e2e.sdk.images.test_images import test_pull_nonexistent_uuid_image_s as _test_pull_nonexistent_uuid_image_s
from tests.e2e.sdk.images.test_images import test_use_strict_by_tag_s as _test_use_strict_by_tag_s
from tests.e2e.sdk.images.test_images import test_use_strict_by_uuid_s as _test_use_strict_by_uuid_s
from tests.e2e.sdk.images.test_images import test_use_strict_nonexistent_tag_s as _test_use_strict_nonexistent_tag_s
from tests.e2e.sdk.images.test_images import test_use_strict_nonexistent_uuid_s as _test_use_strict_nonexistent_uuid_s


# NOTE: `contree_s.images(kind=ImageKind.IMPORTED, ...)` (the old
# `test_get_images_with_parameters_s` e2e scenario) has no unit-test
# counterpart here: `contree_client.base.ContreeSyncClient.list_images` has no
# `kind` filter at all, so that parameter was dropped from
# `ImagesManager(Sync).get_images_list`/`__call__` -- there is nothing left to
# mock or assert.


@pytest.fixture
def api_fake_images_with_404(fake_api, fake_api_s):
    from contree_client.exceptions import NotFoundError

    error = NotFoundError(404, "Image not found")
    for api in (fake_api, fake_api_s):
        api.mock("inspect_image", error=error)
        api.mock("inspect_find_image_by_tag", error=error)
    return fake_api_s


@pytest.mark.parametrize("client_type", ["async", "sync"])
async def test_get_all_images(client_type, fake_contree: Contree, fake_contree_s: ContreeSync, api_fake_images):
    await _test_get_all_images(client_type, fake_contree, fake_contree_s)


def test_pull_image_by_uuid_s(fake_contree_s: ContreeSync, image_uuid, api_fake_images):
    _test_pull_image_by_uuid_s(fake_contree_s, image_uuid)


def test_pull_image_by_tag_s(fake_contree_s: ContreeSync, image_tag, api_fake_images):
    _test_pull_image_by_tag_s(fake_contree_s, image_tag)


def test_pull_nonexistent_uuid_image_s(fake_contree_s: ContreeSync, api_fake_images_with_404):
    _test_pull_nonexistent_uuid_image_s(fake_contree_s)


def test_pull_nonexistent_tag_image_s(fake_contree_s: ContreeSync, api_fake_images_with_404):
    _test_pull_nonexistent_tag_image_s(fake_contree_s)


async def test_iter_images(fake_contree: Contree, api_fake_images):
    await _test_iter_images(fake_contree)


def test_iter_images_s(fake_contree_s: ContreeSync, api_fake_images):
    _test_iter_images_s(fake_contree_s)


def test_oci_image_by_tag_s(fake_contree_s: ContreeSync, image_tag, api_fake_images):
    _test_oci_image_by_tag_s(fake_contree_s, image_tag)


def test_oci_public_image_s(fake_contree_s: ContreeSync, api_fake_images_with_404, api_fake_import):
    _test_oci_public_image_s(fake_contree_s)


def test_oci_nonexistent_uuid_s(fake_contree_s: ContreeSync, api_fake_images_with_404):
    _test_oci_nonexistent_uuid_s(fake_contree_s)


def test_use_strict_by_uuid_s(fake_contree_s: ContreeSync, image_uuid, api_fake_images):
    _test_use_strict_by_uuid_s(fake_contree_s, image_uuid)


def test_use_strict_by_tag_s(fake_contree_s: ContreeSync, image_tag, api_fake_images):
    _test_use_strict_by_tag_s(fake_contree_s, image_tag)


def test_use_strict_nonexistent_uuid_s(fake_contree_s: ContreeSync, api_fake_images_with_404):
    _test_use_strict_nonexistent_uuid_s(fake_contree_s)


def test_use_strict_nonexistent_tag_s(fake_contree_s: ContreeSync, api_fake_images_with_404):
    _test_use_strict_nonexistent_tag_s(fake_contree_s)
