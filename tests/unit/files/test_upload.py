from pathlib import Path

from pytest_httpx import HTTPXMock

from contree_sdk import Contree
from tests.e2e.sdk.files.test_upload import test_upload_file as _test_upload_file


async def test_upload_file(fake_contree: Contree, test_txt_path: Path, api_fake_upload: HTTPXMock):
    await _test_upload_file(fake_contree, test_txt_path)
