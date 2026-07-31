import json
from uuid import UUID

from pytest_httpx import HTTPXMock

from contree_sdk import ContreeSync
from tests.e2e.sdk.images.test_images import test_import_not_real_image_s as _test_import_not_real_image_s
from tests.e2e.sdk.images.test_images import test_import_public_image_s as _test_import_public_image_s


def test_import_public_image_s(fake_contree_s: ContreeSync, api_fake_import: HTTPXMock):
    _test_import_public_image_s(fake_contree_s)


def test_import_with_tag_override_s(fake_contree_s: ContreeSync, result_image_uuid: UUID, api_fake_import: HTTPXMock):
    image = fake_contree_s.images.import_from("docker://ghcr.io/linuxserver/code-server:latest", tag="override")

    assert image.uuid == result_image_uuid
    assert image.tag == "override"

    [import_request] = [
        request
        for request in api_fake_import.get_requests()
        if request.method == "POST" and request.url.path.endswith("/images/import")
    ]
    assert json.loads(import_request.read().decode())["tag"] == "override"


def test_pull_import_not_real_image_s(fake_contree_s: ContreeSync, api_fake_import_failed: HTTPXMock):
    _test_import_not_real_image_s(fake_contree_s)
