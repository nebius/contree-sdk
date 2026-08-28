from hashlib import sha256
from pathlib import Path

import pytest

from contree_sdk import Contree
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
