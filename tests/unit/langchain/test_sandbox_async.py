import asyncio

import pytest
from contree_client.exceptions import NotFoundError
from contree_client.models import FileResponse
from contree_client.testing import ContreeAsyncClient


pytest.importorskip("deepagents")

from contree_sdk.langchain import ContreeAsyncSandbox
from contree_sdk.session import ContreeAsyncSession
from tests.unit.session.factories import mock_completion, operation_response, spawn_response


@pytest.fixture
def client() -> ContreeAsyncClient:
    client = ContreeAsyncClient()
    client.mock("resolve_image", "base")
    return client


@pytest.fixture
def sandbox(client: ContreeAsyncClient) -> ContreeAsyncSandbox:
    return ContreeAsyncSandbox(ContreeAsyncSession(client, image="base"))


async def test_execute_serializes_mutations(client, sandbox):
    client.mock("spawn_instance", spawn_response("first"))
    client.mock("spawn_instance", spawn_response("second"))
    mock_completion(client, operation_response(result_image_uuid="first", stdout="out", stderr="err"))
    mock_completion(client, operation_response(result_image_uuid="second", exit_code=3))
    results = await asyncio.gather(sandbox.aexecute("one"), sandbox.aexecute("two"))
    assert results[0].output == "outerr"
    assert results[1].exit_code == 3
    entries, _ = await sandbox.session.history()
    assert entries[2].parent_id == entries[1].id
    assert client.calls_for("spawn_instance")[1].args[1] == "first"


async def test_upload_preserves_valid_paths(client, sandbox):
    client.mock("ensure_file", FileResponse(uuid="file", sha256="hash", size=4))
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response())
    responses = await sandbox.aupload_files([("/file", b"data"), ("relative", b"data")])
    assert [response.error for response in responses] == [None, "invalid_path"]
    assert len(client.calls_for("ensure_file")) == 1


async def test_download_uses_image_inspection(client, sandbox):
    client.mock("inspect_image_download", b"\x00\xff")
    client.mock("inspect_image_download", error=NotFoundError(404, "missing"))
    responses = await sandbox.adownload_files(["/file", "/missing", "relative"])
    assert responses[0].content == b"\x00\xff"
    assert responses[1].error == "file_not_found"
    assert responses[2].error == "invalid_path"
    assert client.calls_for("spawn_instance") == []


def test_sync_methods_require_async_counterparts(sandbox):
    with pytest.raises(NotImplementedError, match="aexecute"):
        sandbox.execute("echo")
    with pytest.raises(NotImplementedError, match="aupload_files"):
        sandbox.upload_files([])
    with pytest.raises(NotImplementedError, match="adownload_files"):
        sandbox.download_files([])
