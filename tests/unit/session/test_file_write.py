import inspect
import shlex
from pathlib import PurePosixPath

import pytest
from contree_client.models import InstanceResult, InstanceResultState, StreamRepr

from contree_sdk import AsyncExecutor, RunRequest, SyncExecutor
from contree_sdk.exceptions import FileWriteError


class Writer(SyncExecutor):
    session_id = "writer"

    def __init__(self):
        self.requests = []
        self.result = InstanceResult(state=InstanceResultState(exit_code=0))

    def execute(self, request: RunRequest) -> InstanceResult:
        self.requests.append(request)
        return self.result

    def read_file(self, path: str) -> bytes:
        raise NotImplementedError


class AsyncWriter(AsyncExecutor):
    session_id = "writer"

    def __init__(self):
        self.requests = []
        self.result = InstanceResult(state=InstanceResultState(exit_code=0))

    async def execute(self, request: RunRequest) -> InstanceResult:
        self.requests.append(request)
        return self.result

    async def read_file(self, path: str) -> bytes:
        raise NotImplementedError


@pytest.fixture(params=[Writer, AsyncWriter], ids=["sync", "async"])
def writer(request):
    return request.param()


async def write(writer, path, content):
    pending = writer.write_file(path, content)
    if inspect.isawaitable(pending):
        await pending


async def test_write_quotes_guest_paths_and_keeps_content_in_stdin(writer):
    path = "/dir with 'quotes'/file; $(echo injected) `echo injected`\n.txt"
    content = bytes(range(256))
    await write(writer, path, content)
    request = writer.requests[0]
    assert shlex.split(request.shell) == ["mkdir", "-p", "--", str(PurePosixPath(path).parent), "&&", "cat", ">", path]
    assert request.stdin == content
    assert not request.files


@pytest.mark.parametrize("path", ["relative", "", "/bad\x00path"])
async def test_write_rejects_invalid_path_before_execute(writer, path):
    with pytest.raises(ValueError, match="absolute"):
        await write(writer, path, b"content")
    assert not writer.requests


@pytest.mark.parametrize("exit_code", [1, None, Ellipsis])
async def test_write_requires_confirmed_success(writer, exit_code):
    writer.result = InstanceResult(state=InstanceResultState(exit_code=exit_code))
    with pytest.raises(FileWriteError, match="write command failed") as caught:
        await write(writer, "/file", b"content")
    assert caught.value.path == "/file"


async def test_write_reports_remote_stderr(writer):
    writer.result = InstanceResult(state=InstanceResultState(exit_code=1), stderr=StreamRepr.from_text("disk full"))
    with pytest.raises(FileWriteError) as caught:
        await write(writer, "/file", b"content")
    assert caught.value.message == "disk full"
