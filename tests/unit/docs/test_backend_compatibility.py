"""Verify the file-transfer limits documented for LangChain DeepAgents."""

import pytest

from contree_sdk import AsyncLazySession, ContreeAsyncSession, ContreeSession, LazySession
from contree_sdk.session.base import stream_repr_for_stdin


@pytest.mark.parametrize("warm", [False, True])
def test_lazy_sandbox_uploads_in_same_vm_and_reads_without_snapshot(lazy_api, warm):
    pytest.importorskip("deepagents")
    from contree_sdk.langchain import ContreeSandbox

    client = lazy_api.sync
    client.mock("inspect_instance_download", b"saved")
    with LazySession(ContreeSession(client, image="base")) as lazy:
        sandbox = ContreeSandbox(lazy)
        if warm:
            sandbox.execute("echo saved > /result.txt")
        assert sandbox.upload_files([("/input.txt", b"input")])[0].error is None
        assert sandbox.upload_files([("/empty.txt", b"")])[0].error is None
        sandbox.execute("cat /input.txt")
        assert len(client.calls_for("spawn_instance")) == 1
        assert not client.calls_for("get_operation_status")
        uploads = client.calls_for("operation_subprocess_create")[int(warm) : int(warm) + 2]
        assert [call.kwargs["stdin"] for call in uploads] == [
            stream_repr_for_stdin(data, close=True) for data in (b"input", b"")
        ]
        assert sandbox.download_files(["/result.txt"])[0].content == b"saved"
        assert lazy.phase == "running"
        assert lazy.last_entry is None
        assert not client.calls_for("operation_subprocess_kill")
        assert client.calls_for("inspect_instance_download")[0].args == ("op-1", "/result.txt")


@pytest.mark.parametrize("warm", [False, True])
async def test_async_lazy_sandbox_has_the_same_file_boundaries(lazy_api, warm):
    pytest.importorskip("deepagents")
    from contree_sdk.langchain import ContreeAsyncSandbox

    client = lazy_api.async_client
    client.mock("inspect_instance_download", b"saved")
    async with AsyncLazySession(ContreeAsyncSession(client, image="base")) as lazy:
        sandbox = ContreeAsyncSandbox(lazy)
        if warm:
            await sandbox.aexecute("echo saved > /result.txt")
        assert (await sandbox.aupload_files([("/input.txt", b"input")]))[0].error is None
        assert (await sandbox.aupload_files([("/empty.txt", b"")]))[0].error is None
        await sandbox.aexecute("cat /input.txt")
        assert len(client.calls_for("spawn_instance")) == 1
        assert not client.calls_for("get_operation_status")
        uploads = client.calls_for("operation_subprocess_create")[int(warm) : int(warm) + 2]
        assert [call.kwargs["stdin"] for call in uploads] == [
            stream_repr_for_stdin(data, close=True) for data in (b"input", b"")
        ]
        assert (await sandbox.adownload_files(["/result.txt"]))[0].content == b"saved"
        assert lazy.phase == "running"
        assert lazy.last_entry is None
        assert not client.calls_for("operation_subprocess_kill")
        assert client.calls_for("inspect_instance_download")[0].args == ("op-1", "/result.txt")
