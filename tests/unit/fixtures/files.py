from uuid import uuid4

import pytest
from pytest_httpx import HTTPXMock

from tests.unit.fixtures.utils import r


@pytest.fixture
def file_uuid() -> str:
    return str(uuid4())


@pytest.fixture
def file_sha256() -> str:
    return "1c338c24f4a82e6dc440204d8d6a08058a58136d3e01b4f7aa0f7588b51ba197"


def add_file_responses(httpx_mock: HTTPXMock, file_uuid: str, file_sha256: str):
    httpx_mock.add_response(
        method="GET",
        url=r(".*/files/[0-9a-f]{64}$"),
        status_code=404,
        json={"error": "File not found", "status": 404},
        is_optional=True,
    )
    httpx_mock.add_response(
        method="POST",
        url=r(".*/files"),
        json={"uuid": file_uuid, "sha256": file_sha256, "size": 4},
        is_optional=True,
    )


@pytest.fixture
def api_fake_upload(file_uuid: str, file_sha256: str, strict_httpx: HTTPXMock) -> HTTPXMock:
    add_file_responses(strict_httpx, file_uuid, file_sha256)
    return strict_httpx
