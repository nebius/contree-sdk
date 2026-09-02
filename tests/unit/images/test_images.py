from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from contree_client.models import Image, ImageListResponse
from contree_client.testing import ContreeAsyncClient, ContreeClient

import contree_sdk.sdk.managers.images._async as images_async_module
import contree_sdk.sdk.managers.images._sync as images_sync_module
from contree_sdk import Contree, ContreeSync
from tests.e2e.sdk.images.test_images import test_get_all_images as _test_get_all_images
from tests.e2e.sdk.images.test_images import test_iter_images as _test_iter_images
from tests.e2e.sdk.images.test_images import test_iter_images_s as _test_iter_images_s
from tests.e2e.sdk.images.test_images import test_oci_image_by_tag as _test_oci_image_by_tag
from tests.e2e.sdk.images.test_images import test_oci_image_by_tag_s as _test_oci_image_by_tag_s
from tests.e2e.sdk.images.test_images import test_oci_nonexistent_uuid as _test_oci_nonexistent_uuid
from tests.e2e.sdk.images.test_images import test_oci_nonexistent_uuid_s as _test_oci_nonexistent_uuid_s
from tests.e2e.sdk.images.test_images import test_oci_public_image as _test_oci_public_image
from tests.e2e.sdk.images.test_images import test_oci_public_image_s as _test_oci_public_image_s
from tests.e2e.sdk.images.test_images import test_use_strict_by_tag as _test_use_strict_by_tag
from tests.e2e.sdk.images.test_images import test_use_strict_by_tag_s as _test_use_strict_by_tag_s
from tests.e2e.sdk.images.test_images import test_use_strict_by_uuid as _test_use_strict_by_uuid
from tests.e2e.sdk.images.test_images import test_use_strict_by_uuid_s as _test_use_strict_by_uuid_s
from tests.e2e.sdk.images.test_images import test_use_strict_nonexistent_tag as _test_use_strict_nonexistent_tag
from tests.e2e.sdk.images.test_images import test_use_strict_nonexistent_tag_s as _test_use_strict_nonexistent_tag_s
from tests.e2e.sdk.images.test_images import test_use_strict_nonexistent_uuid as _test_use_strict_nonexistent_uuid
from tests.e2e.sdk.images.test_images import test_use_strict_nonexistent_uuid_s as _test_use_strict_nonexistent_uuid_s
from tests.unit.fixtures.images import queue_image_lookup
from tests.unit.fixtures.imports import queue_import


# NOTE: `contree_s.images(kind=ImageKind.IMPORTED, ...)` (the old
# `test_get_images_with_parameters_s` e2e scenario) has no unit-test
# counterpart here: `contree_client.base.ContreeSyncClient.list_images` has no
# `kind` filter at all, so that parameter was dropped from
# `ImagesManager(Sync).get_images_list`/`__call__` -- there is nothing left to
# mock or assert.

# NOTE: `test_pull_image_by_uuid_s`/`test_pull_image_by_tag_s`/
# `test_pull_nonexistent_uuid_image_s`/`test_pull_nonexistent_tag_image_s` are
# gone -- `ImagesManager(Sync).pull`/`pull_image` were removed entirely from
# the SDK, there is nothing left here to test.


@pytest.fixture
def api_fake_images_with_404(fake_api: ContreeAsyncClient, fake_api_s: ContreeClient) -> None:
    from contree_client.exceptions import NotFoundError

    error = NotFoundError(404, "Image not found")
    for api in (fake_api, fake_api_s):
        api.mock("inspect_image", error=error)
        api.mock("inspect_find_image_by_tag", error=error)


@pytest.mark.parametrize("client_type", ["async", "sync"])
async def test_get_all_images(
    client_type,
    fake_contree: Contree,
    fake_contree_s: ContreeSync,
    fake_api: ContreeAsyncClient,
    fake_api_s: ContreeClient,
    image_uuid: UUID,
    image_tag: str,
):
    queue_image_lookup(fake_api, image_uuid, image_tag)
    queue_image_lookup(fake_api_s, image_uuid, image_tag)
    await _test_get_all_images(client_type, fake_contree, fake_contree_s)


async def test_iter_images(fake_contree: Contree, fake_api: ContreeAsyncClient, image_uuid: UUID, image_tag: str):
    queue_image_lookup(fake_api, image_uuid, image_tag)
    await _test_iter_images(fake_contree)


def test_iter_images_s(fake_contree_s: ContreeSync, fake_api_s: ContreeClient, image_uuid: UUID, image_tag: str):
    queue_image_lookup(fake_api_s, image_uuid, image_tag)
    _test_iter_images_s(fake_contree_s)


async def test_oci_image_by_tag(fake_contree: Contree, fake_api: ContreeAsyncClient, image_uuid: UUID, image_tag: str):
    queue_image_lookup(fake_api, image_uuid, image_tag)
    await _test_oci_image_by_tag(fake_contree, image_tag)


def test_oci_image_by_tag_s(fake_contree_s: ContreeSync, fake_api_s: ContreeClient, image_uuid: UUID, image_tag: str):
    queue_image_lookup(fake_api_s, image_uuid, image_tag)
    _test_oci_image_by_tag_s(fake_contree_s, image_tag)


async def test_oci_public_image(
    fake_contree: Contree, fake_api: ContreeAsyncClient, api_fake_images_with_404, result_image_uuid: UUID
):
    queue_import(fake_api, result_image_uuid=result_image_uuid)
    await _test_oci_public_image(fake_contree)


def test_oci_public_image_s(
    fake_contree_s: ContreeSync, fake_api_s: ContreeClient, api_fake_images_with_404, result_image_uuid: UUID
):
    queue_import(fake_api_s, result_image_uuid=result_image_uuid)
    _test_oci_public_image_s(fake_contree_s)


async def test_oci_nonexistent_uuid(fake_contree: Contree, api_fake_images_with_404):
    await _test_oci_nonexistent_uuid(fake_contree)


def test_oci_nonexistent_uuid_s(fake_contree_s: ContreeSync, api_fake_images_with_404):
    _test_oci_nonexistent_uuid_s(fake_contree_s)


async def test_use_strict_by_uuid(
    fake_contree: Contree, fake_api: ContreeAsyncClient, image_uuid: UUID, image_tag: str
):
    queue_image_lookup(fake_api, image_uuid, image_tag)
    await _test_use_strict_by_uuid(fake_contree, image_uuid)


def test_use_strict_by_uuid_s(fake_contree_s: ContreeSync, fake_api_s: ContreeClient, image_uuid: UUID, image_tag: str):
    queue_image_lookup(fake_api_s, image_uuid, image_tag)
    _test_use_strict_by_uuid_s(fake_contree_s, image_uuid)


async def test_use_strict_by_tag(fake_contree: Contree, fake_api: ContreeAsyncClient, image_uuid: UUID, image_tag: str):
    queue_image_lookup(fake_api, image_uuid, image_tag)
    await _test_use_strict_by_tag(fake_contree, image_tag)


def test_use_strict_by_tag_s(fake_contree_s: ContreeSync, fake_api_s: ContreeClient, image_uuid: UUID, image_tag: str):
    queue_image_lookup(fake_api_s, image_uuid, image_tag)
    _test_use_strict_by_tag_s(fake_contree_s, image_tag)


async def test_use_strict_nonexistent_uuid(fake_contree: Contree, api_fake_images_with_404):
    await _test_use_strict_nonexistent_uuid(fake_contree)


def test_use_strict_nonexistent_uuid_s(fake_contree_s: ContreeSync, api_fake_images_with_404):
    _test_use_strict_nonexistent_uuid_s(fake_contree_s)


async def test_use_strict_nonexistent_tag(fake_contree: Contree, api_fake_images_with_404):
    await _test_use_strict_nonexistent_tag(fake_contree)


def test_use_strict_nonexistent_tag_s(fake_contree_s: ContreeSync, api_fake_images_with_404):
    _test_use_strict_nonexistent_tag_s(fake_contree_s)


async def test_get_image_by_uuid_string(
    fake_contree: Contree, fake_api: ContreeAsyncClient, image_uuid: UUID, image_tag: str
):
    queue_image_lookup(fake_api, image_uuid, image_tag)
    image = await fake_contree.images.get_image_by_uuid(str(image_uuid))
    assert image.uuid == image_uuid


def test_get_image_by_uuid_string_s(
    fake_contree_s: ContreeSync, fake_api_s: ContreeClient, image_uuid: UUID, image_tag: str
):
    queue_image_lookup(fake_api_s, image_uuid, image_tag)
    image = fake_contree_s.images.get_image_by_uuid(str(image_uuid))
    assert image.uuid == image_uuid


async def test_iter_images_resolves_relative_since_to_stable_datetime(fake_api: ContreeAsyncClient, monkeypatch):
    now = datetime(2026, 1, 1, 12, 0, 0)

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(images_async_module, "datetime", FakeDateTime)

    contree = Contree(fake_api, images_list_batch_size=1)
    fake_api.mock("list_images", ImageListResponse(images=[Image(uuid=str(uuid4()), tag="a")]))
    fake_api.mock("list_images", ImageListResponse(images=[]))

    result = [image async for image in contree.images.iter_images(since=timedelta(hours=1))]
    assert len(result) == 1

    expected_since = now - timedelta(hours=1)
    first_call, second_call = fake_api.calls_for("list_images")
    assert first_call.kwargs["since"] == expected_since
    assert second_call.kwargs["since"] == expected_since


def test_iter_images_resolves_relative_since_to_stable_datetime_s(fake_api_s: ContreeClient, monkeypatch):
    now = datetime(2026, 1, 1, 12, 0, 0)

    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(images_sync_module, "datetime", FakeDateTime)

    contree_s = ContreeSync(fake_api_s, images_list_batch_size=1)
    fake_api_s.mock("list_images", ImageListResponse(images=[Image(uuid=str(uuid4()), tag="a")]))
    fake_api_s.mock("list_images", ImageListResponse(images=[]))

    result = list(contree_s.images.iter_images(since=timedelta(hours=1)))
    assert len(result) == 1

    expected_since = now - timedelta(hours=1)
    first_call, second_call = fake_api_s.calls_for("list_images")
    assert first_call.kwargs["since"] == expected_since
    assert second_call.kwargs["since"] == expected_since


async def test_oci_with_tag_override(
    fake_contree: Contree, fake_api: ContreeAsyncClient, api_fake_images_with_404, result_image_uuid: UUID
):
    queue_import(fake_api, result_image_uuid=result_image_uuid)
    image = await fake_contree.images.oci("docker://ghcr.io/linuxserver/code-server:latest", tag="renamed")

    assert image.tag == "renamed"
    [call] = fake_api.calls_for("import_image")
    assert call.kwargs["tag"] == "renamed"


def test_oci_with_tag_override_s(
    fake_contree_s: ContreeSync, fake_api_s: ContreeClient, api_fake_images_with_404, result_image_uuid: UUID
):
    queue_import(fake_api_s, result_image_uuid=result_image_uuid)
    image = fake_contree_s.images.oci("docker://ghcr.io/linuxserver/code-server:latest", tag="renamed")

    assert image.tag == "renamed"
    [call] = fake_api_s.calls_for("import_image")
    assert call.kwargs["tag"] == "renamed"
