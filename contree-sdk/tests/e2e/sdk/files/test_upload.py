from pathlib import Path

from contree_sdk import Contree
from contree_sdk.utils.objects.file import UploadedFile


async def test_upload_file(contree: Contree, test_txt_path: Path):
    res = await contree.files.upload(test_txt_path)
    assert isinstance(res, UploadedFile)
