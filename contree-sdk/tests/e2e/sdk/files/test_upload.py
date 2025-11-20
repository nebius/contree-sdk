from pathlib import Path

from contree_sdk import Contree
from contree_sdk.utils.objects.file import UploadedFile
from tests import data


test_data_path = Path(data.__file__).parent
test_txt_path = test_data_path / "example.txt"


async def test_upload_file(contree: Contree):
    res = await contree.files.upload(test_txt_path)
    assert isinstance(res, UploadedFile)
