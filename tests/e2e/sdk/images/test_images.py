from datetime import datetime, timedelta
from uuid import UUID, uuid4

import pytest
from contree_client.exceptions import NotFoundError

from contree_sdk import Contree, ContreeSync
from contree_sdk.sdk.exceptions import FailedOperationError, OperationTimedOutError
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.sdk.objects.image_like.state import ImageState
from contree_sdk.utils.models.image import ImageKind


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


async def test_oci_image_by_tag(contree: Contree, image_tag):
    image = await contree.images.oci(image_tag, tag="")

    assert isinstance(image.uuid, UUID)
    assert isinstance(image, ContreeImage)
    assert image.tag == image_tag


def test_oci_image_by_tag_s(contree_s: ContreeSync, image_tag):
    image = contree_s.images.oci(image_tag, tag="")

    assert isinstance(image.uuid, UUID)
    assert isinstance(image, ContreeImageSync)
    assert image.tag == image_tag


async def test_oci_public_image(contree: Contree):
    url = "docker://ghcr.io/linuxserver/code-server:latest"
    image = await contree.images.oci(url, timeout=250)
    assert isinstance(image, ContreeImage)
    assert isinstance(image.uuid, UUID)
    assert image.state == ImageState.PULLED
    assert image.tag
    assert "code-server:latest" in image.tag


def test_oci_public_image_s(contree_s: ContreeSync):
    url = "docker://ghcr.io/linuxserver/code-server:latest"
    image = contree_s.images.oci(url, timeout=250)
    assert isinstance(image, ContreeImageSync)
    assert isinstance(image.uuid, UUID)
    assert image.state == ImageState.PULLED
    assert image.tag
    assert "code-server:latest" in image.tag


async def test_oci_nonexistent_uuid(contree: Contree):
    with pytest.raises(NotFoundError):
        await contree.images.oci(uuid4())


def test_oci_nonexistent_uuid_s(contree_s: ContreeSync):
    with pytest.raises(NotFoundError):
        contree_s.images.oci(uuid4())


async def test_use_strict_by_uuid(contree: Contree, image_uuid):
    image = await contree.images.use(str(image_uuid), strict=True)
    assert isinstance(image.uuid, UUID)
    assert isinstance(image, ContreeImage)
    assert image.uuid == image_uuid


def test_use_strict_by_uuid_s(contree_s: ContreeSync, image_uuid):
    image = contree_s.images.use(str(image_uuid), strict=True)
    assert isinstance(image.uuid, UUID)
    assert isinstance(image, ContreeImageSync)
    assert image.uuid == image_uuid


async def test_use_strict_by_tag(contree: Contree, image_tag):
    image = await contree.images.use(image_tag, strict=True)
    assert isinstance(image.uuid, UUID)
    assert isinstance(image, ContreeImage)
    assert image.tag == image_tag


def test_use_strict_by_tag_s(contree_s: ContreeSync, image_tag):
    image = contree_s.images.use(image_tag, strict=True)
    assert isinstance(image.uuid, UUID)
    assert isinstance(image, ContreeImageSync)
    assert image.tag == image_tag


async def test_use_strict_nonexistent_uuid(contree: Contree):
    with pytest.raises(NotFoundError):
        await contree.images.use(uuid4(), strict=True)


def test_use_strict_nonexistent_uuid_s(contree_s: ContreeSync):
    with pytest.raises(NotFoundError):
        contree_s.images.use(uuid4(), strict=True)


async def test_use_strict_nonexistent_tag(contree: Contree):
    with pytest.raises(NotFoundError):
        await contree.images.use("totally-random-tag-" + str(uuid4())[:4], strict=True)


def test_use_strict_nonexistent_tag_s(contree_s: ContreeSync):
    with pytest.raises(NotFoundError):
        contree_s.images.use("totally-random-tag-" + str(uuid4())[:4], strict=True)


@pytest.mark.xfail(raises=OperationTimedOutError, reason="server does not emit events for import operations yet")
async def test_import_public_image(contree: Contree):
    url = "docker://ghcr.io/linuxserver/code-server:latest"
    image = await contree.images.import_from(url, timeout=250)
    assert isinstance(image, ContreeImage)
    assert isinstance(image.uuid, UUID)
    assert image.tag == "ghcr.io/linuxserver/code-server:latest"
    assert image.state == ImageState.PULLED


@pytest.mark.xfail(raises=OperationTimedOutError, reason="server does not emit events for import operations yet")
def test_import_public_image_s(contree_s: ContreeSync):
    url = "docker://ghcr.io/linuxserver/code-server:latest"
    image = contree_s.images.import_from(url, timeout=250)
    assert isinstance(image, ContreeImageSync)
    assert isinstance(image.uuid, UUID)
    assert image.tag == "ghcr.io/linuxserver/code-server:latest"
    assert image.state == ImageState.PULLED


@pytest.mark.xfail(raises=OperationTimedOutError, reason="server does not emit events for import operations yet")
async def test_import_not_real_image(contree: Contree):
    url = f"docker://ghcr.io/linuxserver/random-image-{uuid4()}:latest"
    with pytest.raises(FailedOperationError):
        await contree.images.import_from(url)


@pytest.mark.xfail(raises=OperationTimedOutError, reason="server does not emit events for import operations yet")
def test_import_not_real_image_s(contree_s: ContreeSync):
    url = f"docker://ghcr.io/linuxserver/random-image-{uuid4()}:latest"
    with pytest.raises(FailedOperationError):
        contree_s.images.import_from(url)


# todo add test for private import


async def test_iter_images(contree: Contree):
    num = 0
    async for image in contree.images:
        assert isinstance(image, ContreeImage)
        assert isinstance(image.uuid, UUID)
        num += 1
    assert num > 0


def test_iter_images_s(contree_s: ContreeSync):
    num = 0
    for image in contree_s.images:
        assert isinstance(image, ContreeImageSync)
        assert isinstance(image.uuid, UUID)
        num += 1
    assert num > 0


def test_get_images_with_parameters_s(contree_s: ContreeSync):
    images = contree_s.images(
        number=2,
        kind=ImageKind.IMPORTED,
        tagged=True,
        since=datetime(2025, month=1, day=1),  # since 2025 January 1st
        until=timedelta(minutes=10),  # until 10 minutes ago
    )
    assert len(images) == 2
    for image in images:
        assert isinstance(image, ContreeImageSync)
        assert isinstance(image.uuid, UUID)
        assert isinstance(image.tag, str)
