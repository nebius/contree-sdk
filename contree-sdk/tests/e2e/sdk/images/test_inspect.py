from os import urandom
from pathlib import Path
from tempfile import NamedTemporaryFile

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.sdk.objects.image_fs._async import ImageDirectory, ImageFile
from contree_sdk.sdk.objects.image_fs._sync import ImageFileSync
from contree_sdk.sdk.objects.image_like._sync import ImageDirectorySync


_path_etc = "/etc"


async def test_image_ls(image: ContreeImage):
    items = await image.ls(_path_etc)
    assert len(items) > 1
    directory = None
    for item in items:
        assert isinstance(item, ImageFile | ImageDirectory)
        assert str(item.full_path).startswith(_path_etc)

        if isinstance(item, ImageDirectory):
            directory = item
    assert directory is not None
    subitems = await directory.ls()
    assert subitems
    for item in subitems:
        assert isinstance(item, ImageFile | ImageDirectory)
        assert str(item.full_path).startswith(str(directory.full_path))


def test_image_ls_s(image_s: ContreeImageSync):
    items = image_s.ls("/etc")
    assert len(items) > 1
    directory = None
    for item in items:
        assert isinstance(item, ImageFileSync | ImageDirectorySync)
        assert str(item.full_path).startswith(_path_etc)

        if isinstance(item, ImageDirectorySync):
            directory = item

    subitems = directory.ls()
    assert subitems
    for item in subitems:
        assert isinstance(item, ImageFileSync | ImageDirectorySync)
        assert str(item.full_path).startswith(str(directory.full_path))


RANDOM_DATA = b"Some random data\n" + urandom(16)


async def test_download_file(image: ContreeImage):
    res = await image.run(shell="cat > /output.txt", stdin=RANDOM_DATA, disposable=False)
    with NamedTemporaryFile("rb") as f:
        await res.download("/output.txt", f.name)
        assert f.read() == RANDOM_DATA

    res_file = None
    for file in await res.ls():
        if file.full_path == Path("/output.txt"):
            res_file = file
    assert await res_file.read() == RANDOM_DATA


async def test_download_file_s(image_s: ContreeImageSync):
    res = image_s.run(shell="cat > /output.txt", stdin=RANDOM_DATA, disposable=False).wait()
    with NamedTemporaryFile("rb") as f:
        res.download("/output.txt", f.name)
        assert f.read() == RANDOM_DATA

    res_file = None
    for file in res.ls():
        if file.full_path == Path("/output.txt"):
            res_file = file
    assert res_file.read() == RANDOM_DATA
