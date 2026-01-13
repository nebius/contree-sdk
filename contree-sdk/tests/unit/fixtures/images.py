from uuid import UUID, uuid4

import pytest
from pytest_httpx import HTTPXMock

from contree_sdk import Contree, ContreeSync
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from tests.unit.fixtures.utils import r, url


@pytest.fixture()
def image_uuid() -> UUID:
    return uuid4()


@pytest.fixture()
def image_tag() -> str:
    return "busybox:latest"


@pytest.fixture()
def api_fake_images(image_uuid: UUID, image_tag: str, strict_httpx: HTTPXMock) -> HTTPXMock:
    image_dict = {"uuid": str(image_uuid), "tag": image_tag, "created_at": "2024-01-01T12:00:00+00:00"}
    for _ in range(3):
        strict_httpx.add_response(
            method="GET",
            url=r(".*/images"),
            json={"images": [image_dict]},
            is_optional=True,
        )
    strict_httpx.add_response(
        method="GET",
        url=r(f".*/inspect/{image_uuid}$"),
        json=image_dict,
        is_optional=True,
    )
    strict_httpx.add_response(
        method="GET",
        url=url("/inspect", params={"tag": image_tag}),
        json=image_dict,
        is_optional=True,
    )
    return strict_httpx


@pytest.fixture()
def fake_image(fake_contree: Contree, image_uuid: UUID, image_tag: str, api_fake_images: HTTPXMock) -> ContreeImage:
    return ContreeImage(client=fake_contree, uuid=image_uuid, tag=image_tag)


@pytest.fixture()
def fake_image_s(
    fake_contree_s: ContreeSync, image_uuid: UUID, image_tag: str, api_fake_images: HTTPXMock
) -> ContreeImageSync:
    return ContreeImageSync(client=fake_contree_s, uuid=image_uuid, tag=image_tag)


@pytest.fixture()
def api_fake_forbidden(strict_httpx: HTTPXMock) -> HTTPXMock:
    strict_httpx.add_response(
        method="GET",
        url=r(".*/images"),
        status_code=403,
        json={"error": "Forbidden"},
        is_optional=True,
    )
    return strict_httpx
