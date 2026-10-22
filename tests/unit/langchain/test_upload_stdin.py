"""Exercise upload commands against a local shell and the public executor contract."""

import asyncio
import subprocess

import pytest
from contree_client.models import InstanceResult, InstanceResultState, StreamRepr


pytest.importorskip("deepagents")

from contree_sdk import AsyncExecutor, RunRequest, SyncExecutor
from contree_sdk.langchain import ContreeAsyncSandbox, ContreeSandbox


def result(code, stdout, stderr):
    return InstanceResult(
        state=InstanceResultState(exit_code=code),
        stdout=StreamRepr.from_bytes(stdout),
        stderr=StreamRepr.from_bytes(stderr),
    )


class LocalExecutor(SyncExecutor):
    session_id = "local-upload-test"

    def execute(self, request: RunRequest) -> InstanceResult:
        assert request.shell is not None
        assert isinstance(request.stdin, bytes)
        assert not request.files
        completed = subprocess.run(  # noqa: S603 - generated SDK command; test paths are under tmp_path
            ["/bin/sh", "-c", request.shell], input=request.stdin, capture_output=True, timeout=5, check=False
        )
        return result(completed.returncode, completed.stdout, completed.stderr)

    def read_file(self, path: str) -> bytes:
        raise NotImplementedError


class LocalAsyncExecutor(AsyncExecutor):
    session_id = "local-upload-test"

    async def execute(self, request: RunRequest) -> InstanceResult:
        assert request.shell is not None
        assert isinstance(request.stdin, bytes)
        assert not request.files
        process = await asyncio.create_subprocess_exec(
            "/bin/sh",
            "-c",
            request.shell,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(request.stdin), 5)
        return result(process.returncode, stdout, stderr)

    async def read_file(self, path: str) -> bytes:
        raise NotImplementedError


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
async def test_upload_binary_empty_overwrite_and_path_quoting(tmp_path, asynchronous):
    path = tmp_path / "dir with 'quotes'" / "file; $(echo injected) `echo injected`\n.txt"
    path.parent.mkdir()
    path.write_bytes(b"old trailing bytes")
    empty = tmp_path / "new parent" / "empty"
    binary = bytes(range(256)) * 8192
    files = [(str(path), binary), (str(empty), b""), ("relative", b"bad"), ("/nul\x00path", b"bad")]
    if asynchronous:
        responses = await ContreeAsyncSandbox(LocalAsyncExecutor()).aupload_files(files)
    else:
        responses = ContreeSandbox(LocalExecutor()).upload_files(files)
    assert [item.error for item in responses] == [None, None, "invalid_path", "invalid_path"]
    assert path.read_bytes() == binary
    assert empty.read_bytes() == b""
    assert sorted(item.name for item in path.parent.iterdir()) == [path.name]


@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
async def test_failed_write_is_reported_and_next_file_is_attempted(tmp_path, asynchronous):
    directory = tmp_path / "directory"
    directory.mkdir()
    target = tmp_path / "written"
    files = [(str(directory), b"bad"), (str(target), b"ok")]
    if asynchronous:
        responses = await ContreeAsyncSandbox(LocalAsyncExecutor()).aupload_files(files)
    else:
        responses = ContreeSandbox(LocalExecutor()).upload_files(files)
    assert responses[0].error
    assert responses[1].error is None
    assert target.read_bytes() == b"ok"


@pytest.mark.parametrize("error", [OSError("transport"), TimeoutError("timeout")])
def test_upload_preserves_executor_errors(error):
    class FailingExecutor(LocalExecutor):
        def execute(self, request):
            raise error

    adapter = ContreeSandbox(FailingExecutor())
    with pytest.raises(type(error)) as caught:
        adapter.upload_files([("/file", b"data")])
    assert caught.value is error
    assert not adapter.lock.locked()


@pytest.mark.parametrize("error", [OSError("transport"), TimeoutError("timeout"), asyncio.CancelledError()])
async def test_async_upload_preserves_errors_and_cancellation(error):
    class FailingExecutor(LocalAsyncExecutor):
        async def execute(self, request):
            raise error

    adapter = ContreeAsyncSandbox(FailingExecutor())
    with pytest.raises(type(error)) as caught:
        await adapter.aupload_files([("/file", b"data")])
    assert caught.value is error
    assert not adapter.lock.locked()
