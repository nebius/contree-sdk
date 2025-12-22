from os import urandom
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.sdk.objects.image_fs import ImageDirectory, ImageDirectorySync, ImageFile, ImageFileSync


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


@pytest.fixture()
def random_data() -> bytes:
    return b"Some random data\n" + urandom(16)


async def test_download_file(image: ContreeImage, random_data):
    res = await image.run(shell="cat > /output.txt", stdin=random_data, disposable=False)
    with NamedTemporaryFile("rb") as f:
        await res.download("/output.txt", f.name)
        assert f.read() == random_data


async def test_read_file(image: ContreeImage, random_data):
    res = await image.run(shell="cat > /output.txt", stdin=random_data, disposable=False)
    assert await res.read("/output.txt") == random_data

    res_file = None
    for file in await res.ls():
        if file.full_path == Path("/output.txt"):
            res_file = file
    assert await res_file.read() == random_data


def test_download_file_s(image_s: ContreeImageSync, random_data):
    res = image_s.run(shell="cat > /output.txt", stdin=random_data, disposable=False).wait()
    with NamedTemporaryFile("rb") as f:
        res.download("/output.txt", f.name)
        assert f.read() == random_data


def test_read_file_s(image_s: ContreeImageSync, random_data):
    res = image_s.run(shell="cat > /output.txt", stdin=random_data, disposable=False).wait()
    assert res.read("/output.txt") == random_data

    res_file = None
    for file in res.ls():
        if file.full_path == Path("/output.txt"):
            res_file = file
    assert res_file.read() == random_data
