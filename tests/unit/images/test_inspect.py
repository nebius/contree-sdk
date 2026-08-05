from uuid import UUID

import pytest
from contree_client.models import FileItem
from pytest_httpx import HTTPXMock

from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from tests.e2e.sdk.images.test_inspect import test_download_file as _test_download_file
from tests.e2e.sdk.images.test_inspect import test_download_file_s as _test_download_file_s
from tests.e2e.sdk.images.test_inspect import test_image_ls as _test_image_ls
from tests.e2e.sdk.images.test_inspect import test_image_ls_s as _test_image_ls_s
from tests.e2e.sdk.images.test_inspect import test_read_file as _test_read_file
from tests.e2e.sdk.images.test_inspect import test_read_file_s as _test_read_file_s
from tests.unit.fixtures.images import add_tag_responses
from tests.unit.fixtures.utils import url


def create_file_item(name: str, is_dir: bool = False, size: int = 0) -> dict:
    model = FileItem(
        size=size if not is_dir else 4096,
        path=name,
        uid=0,
        gid=0,
        mode=16877 if is_dir else 33188,
        mtime=0,
        nlink=2 if is_dir else 1,
        symlink_to="",
        is_dir=is_dir,
        is_regular=not is_dir,
        is_socket=False,
        is_fifo=False,
        is_symlink=False,
        owner="root",
        group="root",
    )
    return model.to_dict()


def create_etc_files() -> list[dict]:
    return [
        create_file_item("hostname", is_dir=False),
        create_file_item("xdg", is_dir=True),
    ]


def create_xdg_files() -> list[dict]:
    return [
        create_file_item("subfile.txt", is_dir=False),
    ]


def create_output_file(size: int) -> list[dict]:
    return [
        create_file_item("output.txt", is_dir=False, size=size),
    ]


@pytest.fixture
def api_fake_inspect_ls(image_uuid: UUID, api_fake_images: HTTPXMock) -> HTTPXMock:
    api_fake_images.add_response(
        method="GET",
        url=url(f"/v1/inspect/{image_uuid}/list", params={"path": "/etc"}),
        json={"path": "/etc", "files": create_etc_files()},
        is_optional=True,
    )

    api_fake_images.add_response(
        method="GET",
        url=url(f"/v1/inspect/{image_uuid}/list", params={"path": "/etc/xdg"}),
        json={"path": "/etc/xdg", "files": create_xdg_files()},
        is_optional=True,
    )

    return api_fake_images


@pytest.fixture
def api_fake_inspect_download(
    image_uuid: UUID, result_image_uuid: UUID, random_data: bytes, api_fake_run: HTTPXMock
) -> HTTPXMock:
    add_tag_responses(api_fake_run, result_image_uuid)

    download_url = url(f"/v1/inspect/{result_image_uuid}/download", params={"path": "/output.txt"})

    for _ in range(2):
        api_fake_run.add_response(
            method="GET",
            url=download_url,
            content=random_data,
            is_optional=True,
        )

    api_fake_run.add_response(
        method="GET",
        url=url(f"/v1/inspect/{result_image_uuid}/list", params={"path": "/"}),
        json={"path": "/", "files": create_output_file(len(random_data))},
        is_optional=True,
    )

    return api_fake_run


async def test_image_ls(api_fake_inspect_ls: HTTPXMock, fake_image: ContreeImage):
    await _test_image_ls(fake_image)


def test_image_ls_s(api_fake_inspect_ls: HTTPXMock, fake_image_s: ContreeImageSync):
    _test_image_ls_s(fake_image_s)


async def test_download_file(
    api_fake_inspect_download: HTTPXMock, fake_image: ContreeImage, random_data: bytes, tmp_file
):
    await _test_download_file(fake_image, tmp_file, random_data)


async def test_download_streams_chunks_while_read_stays_buffered(fake_image: ContreeImage, tmp_path, mocker):
    async def chunks(*_args):
        for chunk in (b"first", b"second", b"third"):
            yield chunk

    stream_download = mocker.patch.object(fake_image._client._api, "inspect_image_download_stream", side_effect=chunks)
    buffered_download = mocker.patch.object(fake_image._client._api, "inspect_image_download", return_value=b"buffered")
    target = tmp_path / "downloaded"

    assert await fake_image.download("/output.txt", target) == target
    assert target.read_bytes() == b"firstsecondthird"
    stream_download.assert_called_once_with(str(fake_image.uuid), "/output.txt")
    buffered_download.assert_not_awaited()

    assert await fake_image.read("/output.txt") == b"buffered"
    buffered_download.assert_awaited_once_with(str(fake_image.uuid), "/output.txt")


async def test_download_closes_stream_when_local_write_fails(fake_image: ContreeImage, tmp_path, mocker):
    stream_closed = False

    async def chunks(*_args):
        nonlocal stream_closed
        try:
            yield b"data"
        finally:
            stream_closed = True

    mocker.patch.object(fake_image._client._api, "inspect_image_download_stream", side_effect=chunks)
    open_file = mocker.patch("builtins.open", mocker.mock_open())
    open_file.return_value.write.side_effect = OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        await fake_image.download("/output.txt", tmp_path / "downloaded")

    assert stream_closed


def test_download_file_s(
    api_fake_inspect_download: HTTPXMock, tmp_file, fake_image_s: ContreeImageSync, random_data: bytes
):
    _test_download_file_s(fake_image_s, tmp_file, random_data)


async def test_read_file(api_fake_inspect_download: HTTPXMock, fake_image: ContreeImage, random_data: bytes):
    await _test_read_file(fake_image, random_data)


def test_read_file_s(api_fake_inspect_download: HTTPXMock, fake_image_s: ContreeImageSync, random_data: bytes):
    _test_read_file_s(fake_image_s, random_data)
