from hashlib import sha256
from pathlib import Path

import pytest
from contree_client.exceptions import UnprocessableEntityError

from contree_sdk import Contree
from contree_sdk.utils.models.file import UploadFileSpec
from tests.e2e.sdk.files.test_upload import test_upload_file as _test_upload_file
from tests.unit.fixtures.files import queue_upload


@pytest.fixture
def test_txt_sha256(test_txt_path: Path) -> str:
    return sha256(test_txt_path.read_bytes()).hexdigest()


async def test_upload_file(
    fake_contree: Contree,
    test_txt_path: Path,
    file_uuid: str,
    file_sha256: str,
    test_txt_sha256: str,
):
    queue_upload(fake_contree.api, file_uuid, file_sha256)
    await _test_upload_file(fake_contree, test_txt_path)

    [call] = fake_contree.api.calls_for("ensure_file")
    (content,) = call.args
    assert content == test_txt_path.read_bytes()


async def test_prepare_files_for_api_propagates_upload_failure(fake_image):
    fake_image.client.api.mock("ensure_file", error=UnprocessableEntityError(422, "rejected"))
    files = [
        UploadFileSpec(path="/a.txt", source=b"a"),
        UploadFileSpec(path="/b.txt", source=b"b"),
    ]

    with pytest.raises(UnprocessableEntityError):
        await fake_image.prepare_files_for_api(files)


def test_prepare_files_for_api_propagates_upload_failure_s(fake_image_s):
    fake_image_s.client.api.mock("ensure_file", error=UnprocessableEntityError(422, "rejected"))
    files = [
        UploadFileSpec(path="/a.txt", source=b"a"),
        UploadFileSpec(path="/b.txt", source=b"b"),
    ]

    with pytest.raises(UnprocessableEntityError):
        fake_image_s.prepare_files_for_api(files)
