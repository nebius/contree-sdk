from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from contree_client.exceptions import NotFoundError
from contree_client.models import DirectoryList, FileItem, Image, ImageListResponse
from contree_client.testing import ContreeAsyncClient, ContreeClient
from tests.unit.conftest import fake_api, fake_api_s, fake_contree, fake_contree_s
from tests.unit.fixtures.files import file_sha256, file_uuid, queue_upload
from tests.unit.fixtures.images import fake_image_s, image_tag, image_uuid, queue_image_lookup
from tests.unit.fixtures.imports import queue_import, result_image_uuid
from tests.unit.fixtures.operations import operation_id, queue_run
from tests.unit.fixtures.runs import api_fake_popen_communicate, api_fake_popen_shell

from contree_sdk.sdk.objects.image import ContreeImageSync
from contree_sdk.sdk.objects.session import ContreeSessionSync


__all__ = [
    "api_client",
    "api_client_s",
    "api_fake_images",
    "api_fake_popen_communicate",
    "api_fake_popen_shell",
    "api_fake_quick_start",
    "api_fake_session_multiple_runs",
    "api_fake_stable_uuid",
    "docs_file_upload",
    "fake_api",
    "fake_api_s",
    "fake_contree",
    "fake_contree_s",
    "fake_image_s",
    "file_sha256",
    "file_uuid",
    "image",
    "image_tag",
    "image_uuid",
    "operation_id",
    "result_image_uuid",
    "session",
]


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool:
    return "_tmp" in str(collection_path)


# A directory listing entry used for `ls()`/`download()`/`read()` examples: a
# single regular file is enough to exercise both the "iterate directory" and
# the "download a file found while iterating" branches shown in the README.
DIRECTORY_LISTING_FILE = FileItem(
    size=4,
    path="notes.txt",
    owner="root",
    group="root",
    uid=0,
    gid=0,
    mode=0o100644,
    mtime=1700000000,
    nlink=1,
    is_dir=False,
    is_regular=True,
    is_symlink=False,
    is_socket=False,
    is_fifo=False,
    symlink_to="",
)


def bypass_local_filesystem(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Make the README's illustrative local paths (``/local/files/...``) work
    without existing on the real filesystem.

    Reads always return a fixed payload; writes (including the streaming
    ``open(mode="wb")`` that `download()` uses, which `write_bytes` itself
    delegates to) land under `tmp_path` (keyed by the target's file name)
    instead of the literal absolute path shown in the docs.
    """
    payload = b"contree docs fixture content"
    original_open = Path.open

    def read_bytes(path: Path) -> bytes:
        return payload

    def open_(path: Path, mode: str = "r"):
        if any(flag in mode for flag in "wax"):
            path = tmp_path / path.name
        return original_open(path, mode)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(Path, "open", open_)


@pytest.fixture
def api_client(fake_api: ContreeAsyncClient) -> ContreeAsyncClient:
    """The raw async client README's `fixture:api_client` blocks receive directly.

    Tests that need specific mocked responses take this (or `api_client_s`)
    and call `.mock(...)` on it themselves, rather than going through a
    separate pre-mocked object.
    """
    return fake_api


@pytest.fixture
def api_client_s(fake_api_s: ContreeClient) -> ContreeClient:
    """The raw sync client README's `fixture:api_client_s` blocks receive directly."""
    return fake_api_s


@pytest.fixture
def api_fake_images(
    api_client: ContreeAsyncClient, api_client_s: ContreeClient, image_uuid: UUID, image_tag: str
) -> None:
    queue_image_lookup(api_client, image_uuid, image_tag)
    queue_image_lookup(api_client_s, image_uuid, image_tag)


@pytest.fixture
def api_fake_session_multiple_runs(
    api_client: ContreeAsyncClient, api_client_s: ContreeClient, result_image_uuid: UUID
) -> None:
    # a session mutates itself in place, so each queued run must keep handing
    # back a live `uuid` -- otherwise the next `.run()` in the chain sees an
    # unreferenceable (disposed) image and raises `DisposableImageRunError`.
    for api in (api_client, api_client_s):
        for stdout in ("", "some other step\n", "some data"):
            queue_run(api, stdout=stdout, result_image_uuid=str(result_image_uuid))


@pytest.fixture
def api_fake_quick_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    api_client: ContreeAsyncClient,
    api_client_s: ContreeClient,
    image_uuid: UUID,
    result_image_uuid: UUID,
    file_uuid: str,
    file_sha256: str,
) -> None:
    bypass_local_filesystem(monkeypatch, tmp_path)

    listed_image = Image(uuid=str(image_uuid), tag="ubuntu:latest", created_at="2024-01-01T12:00:00+00:00")
    for api in (api_client, api_client_s):
        # `contree.images()` (the plain listing call)
        api.mock("list_images", ImageListResponse(images=[listed_image]))
        # `images.oci("docker://docker.io/busybox:latest")` first checks for
        # an existing "busybox:latest" tag, doesn't find one, then imports it.
        api.mock("inspect_find_image_by_tag", error=NotFoundError(404, "image not found"))
        queue_import(api, result_image_uuid=result_image_uuid)
        # file uploads for the `files=[...]` run() arguments
        queue_upload(api, file_uuid, file_sha256)
        # every run()/session.run() call in the walkthrough
        queue_run(api, stdout="Hello from Contree!\n", stderr="", result_image_uuid=str(result_image_uuid))
        # ls()/download()/read() calls
        api.mock("inspect_image_list", DirectoryList(path="/", files=[DIRECTORY_LISTING_FILE]))
        api.mock("inspect_image_download", b"contree docs fixture content")
        api.mock("inspect_image_download_stream", [b"contree docs fixture content"])


@pytest.fixture
def image(fake_image_s: ContreeImageSync) -> ContreeImageSync:
    return fake_image_s


@pytest.fixture
def session(fake_image_s: ContreeImageSync) -> ContreeSessionSync:
    return fake_image_s.session()


@pytest.fixture
def api_fake_stable_uuid(fake_api_s: ContreeClient, result_image_uuid: UUID) -> None:
    # a single queued run is sticky, so both `image.run(...)` and the
    # follow-up `result0.run(...)` hand back the same `result_image_uuid` --
    # which is exactly the "UUID stays the same" behavior this block asserts.
    queue_run(fake_api_s, stdout="", result_image_uuid=str(result_image_uuid))


@pytest.fixture
def docs_file_upload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    api_client: ContreeAsyncClient,
    file_uuid: str,
    file_sha256: str,
) -> None:
    bypass_local_filesystem(monkeypatch, tmp_path)
    queue_upload(api_client, file_uuid, file_sha256)
