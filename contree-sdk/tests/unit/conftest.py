import re
from re import escape
from uuid import UUID, uuid4

import pytest
from httpx import QueryParams
from pytest_httpx import HTTPXMock

from contree_sdk import Contree, ContreeSync
from contree_sdk.config import ContreeConfig


@pytest.fixture()
def fake_contree_config() -> ContreeConfig:
    return ContreeConfig(
        token="fake-token",
        base_url="https://fake.contree.endpoint",
    )


@pytest.fixture()
def fake_contree(fake_contree_config: ContreeConfig) -> Contree:
    return Contree(config=fake_contree_config)


@pytest.fixture()
def fake_contree_s(fake_contree_config: ContreeConfig) -> ContreeSync:
    return ContreeSync(config=fake_contree_config)


@pytest.fixture()
def strict_httpx(httpx_mock: HTTPXMock) -> HTTPXMock:
    httpx_mock.reset()

    httpx_mock.strict_responses = True
    return httpx_mock


@pytest.fixture()
def image_uuid() -> UUID:
    return uuid4()


@pytest.fixture()
def image_tag() -> str:
    return "busybox:latest"


r = re.compile


def url(path: str, params: dict = None) -> re.Pattern:
    if params is not None:
        path += escape("?" + str(QueryParams(params)))
    return r(".*" + path)


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
        url=r(f".*/inspect/{image_uuid}"),
        json=image_dict,
        is_optional=True,
    )
    strict_httpx.add_response(
        method="GET",
        url=url("/inspect", params={"tag": image_tag}),
        json=image_dict,
        is_optional=True,
    )
    strict_httpx.add_response(
        method="GET",
        url=r(".*/inspect/.*"),
        json={"error": "Image not found", "status": 404},
        is_optional=True,
        status_code=404,
    )
    strict_httpx.add_response(
        method="GET",
        url=r(r".*/inspect\?tag=.*"),
        json={"error": "Image not found", "status": 404},
        is_optional=True,
        status_code=404,
    )
    return strict_httpx
