from uuid import UUID

import pytest
from contree_client.models import DirectoryList, FileItem, GrepMatch, GrepResult

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from tests.e2e.sdk.images.test_inspect import test_download_file as _test_download_file
from tests.e2e.sdk.images.test_inspect import test_download_file_s as _test_download_file_s
from tests.e2e.sdk.images.test_inspect import test_grep as _test_grep
from tests.e2e.sdk.images.test_inspect import test_grep_s as _test_grep_s
from tests.e2e.sdk.images.test_inspect import test_image_ls as _test_image_ls
from tests.e2e.sdk.images.test_inspect import test_image_ls_s as _test_image_ls_s
from tests.e2e.sdk.images.test_inspect import test_read_file as _test_read_file
from tests.e2e.sdk.images.test_inspect import test_read_file_s as _test_read_file_s
from tests.unit.fixtures.images import queue_tag
from tests.unit.fixtures.operations import queue_run


def make_file_item(name: str, *, is_dir: bool = False, size: int = 0) -> FileItem:
    return FileItem(
        size=4096 if is_dir else size,
        path=name,
        owner="root",
        group="root",
        uid=0,
        gid=0,
        mode=16877 if is_dir else 33188,
        mtime=0,
        nlink=2 if is_dir else 1,
        is_dir=is_dir,
        is_regular=not is_dir,
        is_symlink=False,
        is_socket=False,
        is_fifo=False,
        symlink_to="",
    )


@pytest.fixture
def api_fake_inspect_ls(fake_api, fake_api_s):
    for api in (fake_api, fake_api_s):
        api.mock(
            "inspect_image_list",
            DirectoryList(path="/etc", files=[make_file_item("hostname"), make_file_item("xdg", is_dir=True)]),
        )
        api.mock("inspect_image_list", DirectoryList(path="/etc/xdg", files=[make_file_item("subfile.txt")]))
    return fake_api_s


@pytest.fixture
def api_fake_inspect_download(fake_api, fake_api_s, result_image_uuid: UUID, random_data: bytes):
    for api in (fake_api, fake_api_s):
        queue_run(api, result_image_uuid=str(result_image_uuid))
        queue_tag(api, result_image_uuid, "some-tag")
        api.mock("inspect_image_download", random_data)
        api.mock("inspect_image_download_stream", [random_data])
        api.mock(
            "inspect_image_list",
            DirectoryList(path="/", files=[make_file_item("output.txt", size=len(random_data))]),
        )
    return fake_api_s


async def test_image_ls(api_fake_inspect_ls, fake_image: ContreeImage):
    await _test_image_ls(fake_image)


def test_image_ls_s(api_fake_inspect_ls, fake_image_s: ContreeImageSync):
    _test_image_ls_s(fake_image_s)


async def test_download_file(api_fake_inspect_download, fake_image: ContreeImage, random_data: bytes, tmp_file):
    await _test_download_file(fake_image, tmp_file, random_data)


def test_download_file_s(api_fake_inspect_download, tmp_file, fake_image_s: ContreeImageSync, random_data: bytes):
    _test_download_file_s(fake_image_s, tmp_file, random_data)


async def test_read_file(api_fake_inspect_download, fake_image: ContreeImage, random_data: bytes):
    await _test_read_file(fake_image, random_data)


def test_read_file_s(api_fake_inspect_download, fake_image_s: ContreeImageSync, random_data: bytes):
    _test_read_file_s(fake_image_s, random_data)


@pytest.fixture
def api_fake_inspect_grep(fake_api, fake_api_s, result_image_uuid: UUID):
    grep_result = GrepResult(
        path="/",
        patterns=["beta"],
        matches=[
            GrepMatch(
                path="/grep_test.txt",
                line_number=2,
                absolute_offset=6,
                line_text="beta\n",
                line_bytes=5,
                submatches=[],
                type="match",
            )
        ],
        truncated=False,
    )
    for api in (fake_api, fake_api_s):
        queue_run(api, result_image_uuid=str(result_image_uuid))
        api.mock("inspect_image_grep", grep_result)


async def test_grep(api_fake_inspect_grep, fake_image: ContreeImage):
    await _test_grep(fake_image)


def test_grep_s(api_fake_inspect_grep, fake_image_s: ContreeImageSync):
    _test_grep_s(fake_image_s)
