from hashlib import sha256
from pathlib import Path

import pytest

from contree_sdk import Contree
from tests.e2e.sdk.files.test_upload import test_upload_file as _test_upload_file


@pytest.fixture
def test_txt_sha256(test_txt_path: Path) -> str:
    return sha256(test_txt_path.read_bytes()).hexdigest()


async def test_upload_file(
    fake_contree: Contree,
    test_txt_path: Path,
    api_fake_upload,
    test_txt_sha256: str,
):
    await _test_upload_file(fake_contree, test_txt_path)

    [call] = fake_contree.api.calls_for("ensure_file")
    (content,) = call.args
    assert content == test_txt_path.read_bytes()
