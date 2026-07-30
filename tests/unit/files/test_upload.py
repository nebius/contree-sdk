from hashlib import sha256
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from contree_sdk import Contree
from tests.e2e.sdk.files.test_upload import test_upload_file as _test_upload_file
from tests.unit.fixtures.utils import r


@pytest.fixture
def test_txt_sha256(test_txt_path: Path) -> str:
    return sha256(test_txt_path.read_bytes()).hexdigest()


async def test_upload_file(
    fake_contree: Contree,
    test_txt_path: Path,
    api_fake_upload: HTTPXMock,
    test_txt_sha256: str,
):
    await _test_upload_file(fake_contree, test_txt_path)

    get_request, post_request = api_fake_upload.get_requests()
    assert get_request.method == "GET"
    assert get_request.url.path == f"/v1/files/{test_txt_sha256}"
    assert not get_request.url.query
    assert post_request.method == "POST"
    assert post_request.url.path == "/v1/files"


async def test_get_file_by_sha256_uses_path_parameter(
    fake_contree: Contree,
    strict_httpx: HTTPXMock,
    file_uuid: str,
    file_sha256: str,
):
    strict_httpx.add_response(
        method="GET",
        url=r(f".*/files/{file_sha256}$"),
        json={
            "uuid": file_uuid,
            "sha256": file_sha256,
            "size": 4,
            "created_at": "2024-01-01T12:00:00+00:00",
            "updated_at": "2024-01-01T12:00:00+00:00",
        },
    )

    res = await fake_contree._api.get_file(file_sha256)

    assert (res.uuid, res.sha256) == (file_uuid, file_sha256)
    [request] = strict_httpx.get_requests()
    assert request.method == "GET"
    assert request.url.path == f"/v1/files/{file_sha256}"
    assert not request.url.query


async def test_check_file_exists_uses_path_parameter(
    fake_contree: Contree,
    strict_httpx: HTTPXMock,
    file_sha256: str,
):
    strict_httpx.add_response(
        method="HEAD",
        url=r(f".*/files/{file_sha256}$"),
    )

    await fake_contree._api.check_file_exists(file_sha256)

    [request] = strict_httpx.get_requests()
    assert request.method == "HEAD"
    assert request.url.path == f"/v1/files/{file_sha256}"
    assert not request.url.query
