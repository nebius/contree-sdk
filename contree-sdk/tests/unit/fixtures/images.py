from uuid import UUID, uuid4

import pytest
from pytest_httpx import HTTPXMock

from contree_sdk import Contree, ContreeSync
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.utils.models.image import ImageKind
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
    strict_httpx.add_response(
        method="GET",
        url=r(".*/images"),
        json={
            "images": [
                image_dict,
            ]
        },
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
def api_fake_images_with_404(api_fake_images: HTTPXMock) -> HTTPXMock:
    api_fake_images.add_response(
        method="GET",
        url=r(".*/inspect/.*"),
        json={"error": "Image not found", "status": 404},
        is_optional=True,
        status_code=404,
    )
    api_fake_images.add_response(
        method="GET",
        url=r(r".*/inspect\?tag=.*"),
        json={"error": "Image not found", "status": 404},
        is_optional=True,
        status_code=404,
    )
    return api_fake_images


@pytest.fixture()
def fake_image(fake_contree: Contree, image_uuid: UUID, image_tag: str, api_fake_images: HTTPXMock) -> ContreeImage:
    return ContreeImage(client=fake_contree, uuid=image_uuid, tag=image_tag)


@pytest.fixture()
def fake_image_s(
    fake_contree_s: ContreeSync, image_uuid: UUID, image_tag: str, api_fake_images: HTTPXMock
) -> ContreeImageSync:
    return ContreeImageSync(client=fake_contree_s, uuid=image_uuid, tag=image_tag)


@pytest.fixture()
def api_fake_images_with_params(strict_httpx: HTTPXMock) -> HTTPXMock:
    image1 = {"uuid": str(uuid4()), "tag": "test-image-1:latest", "created_at": "2024-01-01T12:00:00+00:00"}
    image2 = {"uuid": str(uuid4()), "tag": "test-image-2:latest", "created_at": "2024-01-01T12:00:00+00:00"}

    strict_httpx.add_response(
        method="GET",
        url=r(
            f".*/images\\?kind={ImageKind.IMPORTED}&limit=2&offset=0&tagged=1&since=2025-01-01T00%3A00%3A00&until=.*"
        ),
        json={"images": [image1, image2]},
        is_optional=True,
    )

    return strict_httpx
