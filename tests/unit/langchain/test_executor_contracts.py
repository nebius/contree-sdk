import pytest
from contree_client.models import InstanceResult, InstanceResultState, StreamRepr


pytest.importorskip("deepagents")

from contree_sdk import AsyncExecutor, RunRequest, SyncExecutor
from contree_sdk.langchain import ContreeAsyncSandbox, ContreeSandbox


def result():
    return InstanceResult(state=InstanceResultState(exit_code=0), stdout=StreamRepr.from_text("custom"))


class CustomExecutor(SyncExecutor):
    session_id = "custom"

    def __init__(self):
        self.requests = []

    def execute(self, request: RunRequest) -> InstanceResult:
        self.requests.append(request)
        return result()

    def read_file(self, path: str) -> bytes:
        return path.encode()


class CustomAsyncExecutor(AsyncExecutor):
    session_id = "custom"

    def __init__(self):
        self.requests = []

    async def execute(self, request: RunRequest) -> InstanceResult:
        self.requests.append(request)
        return result()

    async def read_file(self, path: str) -> bytes:
        return path.encode()


def test_adapter_uses_only_the_executor_contract():
    executor = CustomExecutor()
    sandbox = ContreeSandbox(executor)
    assert sandbox.execute("echo").output == "custom"
    assert sandbox.upload_files([("/file", b"data")])[0].error is None
    assert sandbox.download_files(["/file"])[0].content == b"/file"
    assert executor.requests[0].shell == "echo"
    assert not executor.requests[0].disposable
    assert not executor.requests[1].files
    assert executor.requests[1].stdin == b"data"


async def test_async_adapter_uses_only_the_executor_contract():
    executor = CustomAsyncExecutor()
    sandbox = ContreeAsyncSandbox(executor)
    assert (await sandbox.aexecute("echo")).output == "custom"
    assert (await sandbox.aupload_files([("/file", b"data")]))[0].error is None
    assert (await sandbox.adownload_files(["/file"]))[0].content == b"/file"
    assert executor.requests[0].shell == "echo"
    assert not executor.requests[0].disposable
    assert not executor.requests[1].files
    assert executor.requests[1].stdin == b"data"


def test_upload_uses_custom_writer_without_executing_a_command():
    from contree_sdk.exceptions import FileWriteError

    class Writer(CustomExecutor):
        def __init__(self):
            super().__init__()
            self.writes = []

        def write_file(self, path: str, content: bytes) -> None:
            if path == "/bad":
                raise FileWriteError(path, "backend refused write")
            self.writes.append((path, content))

    executor = Writer()
    adapter = ContreeSandbox(executor)
    responses = adapter.upload_files([("/bad", b"bad"), ("/good", b"\x00\xff")])
    assert [item.error for item in responses] == ["backend refused write", None]
    assert executor.writes == [("/good", b"\x00\xff")]
    assert not executor.requests


async def test_async_upload_uses_custom_writer_without_executing_a_command():
    from contree_sdk.exceptions import FileWriteError

    class Writer(CustomAsyncExecutor):
        def __init__(self):
            super().__init__()
            self.writes = []

        async def write_file(self, path: str, content: bytes) -> None:
            if path == "/bad":
                raise FileWriteError(path, "backend refused write")
            self.writes.append((path, content))

    executor = Writer()
    adapter = ContreeAsyncSandbox(executor)
    responses = await adapter.aupload_files([("/bad", b"bad"), ("/good", b"\x00\xff")])
    assert [item.error for item in responses] == ["backend refused write", None]
    assert executor.writes == [("/good", b"\x00\xff")]
    assert not executor.requests
