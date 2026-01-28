from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile

from contree_sdk import Contree
from contree_sdk.utils.models.file import UploadedFile


async def test_upload_file(contree: Contree, test_txt_path: Path):
    res = await contree.files.upload(test_txt_path)
    assert isinstance(res, UploadedFile)


async def test_upload_random_file(contree: Contree, random_data: bytes):
    with NamedTemporaryFile("wb") as f:
        f.write(random_data)
        f.flush()
        filehash = sha256(random_data).hexdigest()
        res = await contree.files.upload(f.name)
    assert isinstance(res, UploadedFile)
    assert res.sha256 == filehash
