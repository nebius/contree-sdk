"""Tar downloads from both sync and async inspection streams."""

import asyncio
import io
import tarfile

import pytest

from contree_sdk.file_io import extract_tar_download, extract_tar_download_async


def archive_bytes(name: str, content: bytes) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        member = tarfile.TarInfo(name)
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))
    return buffer.getvalue()


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
async def test_archive_download_merges_files_without_replacing_existing_entries(tmp_path, asynchronous):
    payload = archive_bytes("nested/log.txt", b"log\n")
    destination = tmp_path / "logs"
    destination.mkdir()
    (destination / "existing.txt").write_text("keep")
    chunks = [payload[:101], payload[101:]]

    if asynchronous:

        async def source():
            for chunk in chunks:
                yield chunk

        await extract_tar_download_async(source(), destination)
    else:
        await asyncio.to_thread(extract_tar_download, chunks, destination)

    assert (destination / "nested/log.txt").read_bytes() == b"log\n"
    assert (destination / "existing.txt").read_text() == "keep"


async def test_archive_download_rejects_path_escape(tmp_path):
    payload = archive_bytes("../escape.txt", b"bad")

    async def source():
        yield payload

    with pytest.raises(tarfile.FilterError):
        await extract_tar_download_async(source(), tmp_path / "logs")
    assert not (tmp_path / "escape.txt").exists()


async def test_failed_archive_stream_does_not_extract_partial_data(tmp_path):
    payload = archive_bytes("new.txt", b"new")
    destination = tmp_path / "logs"
    destination.mkdir()
    (destination / "existing.txt").write_text("keep")

    async def source():
        yield payload[:200]
        raise OSError("stream disconnected")

    with pytest.raises(OSError, match="stream disconnected"):
        await extract_tar_download_async(source(), destination)
    assert (destination / "existing.txt").read_text() == "keep"
    assert not (destination / "new.txt").exists()
