"""Verify the limitations listed in the architecture guide."""

import pytest

from contree_sdk import AsyncLazySession, ContreeAsyncSession, ContreeSession, LazySession


def test_lazy_sandbox_requires_startup_uploads_and_snapshot_before_download(lazy_api):
    pytest.importorskip("deepagents")
    from contree_sdk.langchain import ContreeSandbox

    client = lazy_api.sync
    client.mock("inspect_image_download", b"saved")
    with LazySession(ContreeSession(client, image="base")) as lazy:
        sandbox = ContreeSandbox(lazy)
        with pytest.raises(ValueError, match="startup configuration"):
            sandbox.upload_files([("/input.txt", b"input")])
        assert not client.calls_for("spawn_instance")
        sandbox.execute("echo saved > /result.txt")
        with pytest.raises(RuntimeError, match="snapshot pending work"):
            sandbox.download_files(["/result.txt"])
        assert not client.calls_for("inspect_image_download")
        entry = lazy.snapshot()
        assert entry is not None
        assert sandbox.download_files(["/result.txt"])[0].content == b"saved"
        assert client.calls_for("inspect_image_download")[0].args == (entry.image_uuid, "/result.txt")


async def test_async_lazy_sandbox_has_the_same_file_boundaries(lazy_api):
    pytest.importorskip("deepagents")
    from contree_sdk.langchain import ContreeAsyncSandbox

    client = lazy_api.async_client
    client.mock("inspect_image_download", b"saved")
    async with AsyncLazySession(ContreeAsyncSession(client, image="base")) as lazy:
        sandbox = ContreeAsyncSandbox(lazy)
        with pytest.raises(ValueError, match="startup configuration"):
            await sandbox.aupload_files([("/input.txt", b"input")])
        assert not client.calls_for("spawn_instance")
        await sandbox.aexecute("echo saved > /result.txt")
        with pytest.raises(RuntimeError, match="snapshot pending work"):
            await sandbox.adownload_files(["/result.txt"])
        assert not client.calls_for("inspect_image_download")
        entry = await lazy.snapshot()
        assert entry is not None
        assert (await sandbox.adownload_files(["/result.txt"]))[0].content == b"saved"
        assert client.calls_for("inspect_image_download")[0].args == (entry.image_uuid, "/result.txt")
