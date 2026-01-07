from dataclasses import asdict
from uuid import UUID

import pytest
from pytest_httpx import HTTPXMock

from contree_sdk._internals.models.file import FileItemModel
from tests.unit.fixtures.utils import url


def create_file_item(name: str, is_dir: bool = False, size: int = 0) -> dict:
    model = FileItemModel(
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
    return asdict(model)


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


@pytest.fixture()
def api_fake_inspect_ls(image_uuid: UUID, api_fake_images: HTTPXMock) -> HTTPXMock:
    api_fake_images.add_response(
        method="GET",
        url=url(f"/v1/inspect/{image_uuid}/list", params={"path": "/etc"}),
        json={"files": create_etc_files()},
        is_optional=True,
    )

    api_fake_images.add_response(
        method="GET",
        url=url(f"/v1/inspect/{image_uuid}/list", params={"path": "/etc/xdg"}),
        json={"files": create_xdg_files()},
        is_optional=True,
    )

    return api_fake_images


@pytest.fixture()
def api_fake_inspect_download(
    image_uuid: UUID, result_image_uuid: UUID, random_data: bytes, api_fake_run: HTTPXMock
) -> HTTPXMock:
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
        json={"files": create_output_file(len(random_data))},
        is_optional=True,
    )

    return api_fake_run
