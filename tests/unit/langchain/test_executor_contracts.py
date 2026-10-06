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
    assert executor.requests[1].files == {"/file": b"data"}


async def test_async_adapter_uses_only_the_executor_contract():
    executor = CustomAsyncExecutor()
    sandbox = ContreeAsyncSandbox(executor)
    assert (await sandbox.aexecute("echo")).output == "custom"
    assert (await sandbox.aupload_files([("/file", b"data")]))[0].error is None
    assert (await sandbox.adownload_files(["/file"]))[0].content == b"/file"
    assert executor.requests[0].shell == "echo"
    assert not executor.requests[0].disposable
    assert executor.requests[1].files == {"/file": b"data"}
