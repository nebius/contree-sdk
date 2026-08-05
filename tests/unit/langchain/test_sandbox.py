from unittest.mock import AsyncMock, sentinel

import pytest

from contree_sdk.langchain.sandbox import ContreeSandbox
from contree_sdk.sdk.objects.image import ContreeImage


class _UnexpectedLock:
    async def __aenter__(self):
        raise AssertionError("upload must not acquire the lock without valid paths")

    async def __aexit__(self, *_):
        return None


@pytest.fixture
def sandbox(fake_image: ContreeImage) -> ContreeSandbox:
    return ContreeSandbox(fake_image.session())


async def test_upload_files_with_only_invalid_paths_skips_remote_calls(
    sandbox: ContreeSandbox, monkeypatch: pytest.MonkeyPatch
):
    upload_file = AsyncMock()
    apply_files = AsyncMock()
    run = AsyncMock()
    monkeypatch.setattr(sandbox._session.client.files, "_upload_bytes_file", upload_file)
    monkeypatch.setattr(sandbox._session, "_apply_files", apply_files)
    monkeypatch.setattr(sandbox._session, "run", run)
    monkeypatch.setattr(sandbox, "_lock", _UnexpectedLock())

    responses = await sandbox.aupload_files([("relative.txt", b"data")])

    assert [(response.path, response.error) for response in responses] == [("relative.txt", "invalid_path")]
    upload_file.assert_not_awaited()
    apply_files.assert_not_awaited()
    run.assert_not_awaited()


async def test_upload_files_with_mixed_paths_applies_only_valid_files(
    sandbox: ContreeSandbox, monkeypatch: pytest.MonkeyPatch
):
    upload_file = AsyncMock(side_effect=[sentinel.first_upload, sentinel.second_upload])
    apply_files = AsyncMock()
    monkeypatch.setattr(sandbox._session.client.files, "_upload_bytes_file", upload_file)
    monkeypatch.setattr(sandbox._session, "_apply_files", apply_files)

    responses = await sandbox.aupload_files([
        ("/first.txt", b"first"),
        ("relative.txt", b"invalid"),
        ("/second.txt", b"second"),
    ])

    assert [(response.path, response.error) for response in responses] == [
        ("/first.txt", None),
        ("relative.txt", "invalid_path"),
        ("/second.txt", None),
    ]
    assert [call.args for call in upload_file.await_args_list] == [(b"first",), (b"second",)]
    apply_files.assert_awaited_once_with({"/first.txt": sentinel.first_upload, "/second.txt": sentinel.second_upload})


async def test_upload_files_with_valid_paths_applies_all_files(
    sandbox: ContreeSandbox, monkeypatch: pytest.MonkeyPatch
):
    upload_file = AsyncMock(side_effect=[sentinel.first_upload, sentinel.second_upload])
    apply_files = AsyncMock()
    monkeypatch.setattr(sandbox._session.client.files, "_upload_bytes_file", upload_file)
    monkeypatch.setattr(sandbox._session, "_apply_files", apply_files)

    responses = await sandbox.aupload_files([("/first.txt", b"first"), ("/second.txt", b"second")])

    assert [(response.path, response.error) for response in responses] == [
        ("/first.txt", None),
        ("/second.txt", None),
    ]
    apply_files.assert_awaited_once_with({"/first.txt": sentinel.first_upload, "/second.txt": sentinel.second_upload})


async def test_download_file_with_invalid_path_skips_remote_read(
    sandbox: ContreeSandbox, monkeypatch: pytest.MonkeyPatch
):
    read = AsyncMock()
    monkeypatch.setattr(sandbox._session, "read", read)

    response = await sandbox._adownload_file("relative.txt")

    assert (response.path, response.error) == ("relative.txt", "invalid_path")
    read.assert_not_awaited()
