from pathlib import Path, PurePosixPath
from uuid import uuid4

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


async def test_download_file(image: ContreeImage, tmp_file: Path, random_data):
    res = await image.run(shell="cat > /output.txt", stdin=random_data, disposable=False)

    await res.download("/output.txt", tmp_file)
    assert tmp_file.read_bytes() == random_data  # noqa: ASYNC240


async def test_read_file(image: ContreeImage, random_data):
    res = await image.run(shell="cat > /output.txt", stdin=random_data, disposable=False)
    assert await res.read("/output.txt") == random_data

    res_file = None
    for file in await res.ls():
        if file.full_path == PurePosixPath("/output.txt"):
            res_file = file
    assert res_file is not None
    assert await res_file.read() == random_data


def test_download_file_s(image_s: ContreeImageSync, tmp_file, random_data):
    res = image_s.run(shell="cat > /output.txt", stdin=random_data, disposable=False).wait()

    res.download("/output.txt", tmp_file)
    assert tmp_file.read_bytes() == random_data


def test_read_file_s(image_s: ContreeImageSync, random_data):
    test_tag = f"test-e2e-{uuid4().hex[:8]}"
    res = image_s.run(shell="cat > /output.txt", stdin=random_data, tag=test_tag, disposable=False).wait()
    assert res.tag == test_tag
    assert res.read("/output.txt") == random_data

    res_file = None
    for file in res.ls():
        if file.full_path == PurePosixPath("/output.txt"):
            res_file = file
    assert res_file.read() == random_data
