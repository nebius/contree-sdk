import base64
import threading

import pytest
from contree_client.models import FileResponse
from contree_client.testing import ContreeClient


pytest.importorskip("deepagents")

import contree_sdk.langchain.sandbox as sandbox_module
from contree_sdk.langchain import ContreeSandbox
from contree_sdk.session import ContreeSession
from contree_sdk.store import SyncMemoryStore
from tests.unit.session.factories import operation_response, spawn_response


@pytest.fixture
def client() -> ContreeClient:
    client = ContreeClient()
    client.mock("resolve_image", "img-uuid-0")
    return client


@pytest.fixture
def sandbox(client: ContreeClient) -> ContreeSandbox:
    session = ContreeSession(client, image="tag:python:3.11", store=SyncMemoryStore())
    return ContreeSandbox(session=session)


def test_id_contains_session_id(sandbox: ContreeSandbox):
    assert sandbox.session.session_id in sandbox.id


def test_init_raises_friendly_error_when_deepagents_unavailable(client: ContreeClient, monkeypatch: pytest.MonkeyPatch):
    # on Python < 3.11 `deepagents` can't be installed at all; ContreeSandbox()
    # must fail with a clear message instead of a bare ModuleNotFoundError
    monkeypatch.setattr(sandbox_module, "DEEPAGENTS_AVAILABLE", False)
    session = ContreeSession(client, image="tag:python:3.11", store=SyncMemoryStore())

    with pytest.raises(ImportError, match="deepagents"):
        ContreeSandbox(session=session)


def test_execute_combines_stdout_and_stderr(client: ContreeClient, sandbox: ContreeSandbox):
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(exit_code=0, stdout="out\n", stderr="err\n"))

    response = sandbox.execute("echo hi")

    assert response.output == "out\nerr\n"
    assert response.exit_code == 0
    assert response.truncated is False


def test_execute_reports_truncated_when_stdout_or_stderr_truncated(client: ContreeClient, sandbox: ContreeSandbox):
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(exit_code=0, stdout="out\n", stderr="", stdout_truncated=True))

    response = sandbox.execute("echo hi")

    assert response.truncated is True


def test_concurrent_execute_calls_are_serialized_into_a_linear_history(client: ContreeClient, sandbox: ContreeSandbox):
    # two agent tool calls can invoke execute() on separate OS threads against the
    # same session at once (deepagents bridges aexecute() via asyncio.to_thread) -
    # without ContreeSandbox's own lock both could read session.image_uuid before
    # either commits, forking history instead of chaining run2 after run1
    client.mock("spawn_instance", spawn_response(operation_uuid="op-1"))
    client.mock("spawn_instance", spawn_response(operation_uuid="op-2"))
    client.mock("wait_operation", operation_response(operation_uuid="op-1", result_image_uuid="img-uuid-1"))
    client.mock("wait_operation", operation_response(operation_uuid="op-2", result_image_uuid="img-uuid-2"))

    threads = [threading.Thread(target=sandbox.execute, args=(cmd,)) for cmd in ("echo one", "echo two")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    entries, _ = sandbox.session.history()
    assert [entry.kind for entry in entries] == ["init", "run", "run"]
    init_entry, run_a, run_b = entries
    # a proper serialization chains run_b after run_a; a race would leave both
    # run entries as siblings of init_entry instead
    assert run_b.parent_id == run_a.id
    assert run_a.parent_id == init_entry.id
    assert sandbox.session.tip_id == run_b.id
    assert sandbox.session.image_uuid == run_b.image_uuid


def test_execute_reports_nonzero_exit_code(client: ContreeClient, sandbox: ContreeSandbox):
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(exit_code=1, stdout="", stderr="boom"))

    response = sandbox.execute("false")

    assert response.exit_code == 1
    assert response.output == "boom"


def test_upload_files_rejects_relative_paths(sandbox: ContreeSandbox):
    responses = sandbox.upload_files([("relative.txt", b"data")])

    assert len(responses) == 1
    assert responses[0].path == "relative.txt"
    assert responses[0].error == "invalid_path"


def test_upload_files_writes_valid_paths_only(client: ContreeClient, sandbox: ContreeSandbox):
    client.mock("ensure_file", FileResponse(uuid="file-uuid-1", sha256="deadbeef", size=4))
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(result_image_uuid="img-uuid-1", exit_code=0))

    responses = sandbox.upload_files([("/app.txt", b"data"), ("relative.txt", b"data")])

    by_path = {r.path: r for r in responses}
    assert by_path["/app.txt"].error is None
    assert by_path["relative.txt"].error == "invalid_path"
    assert len(client.calls_for("ensure_file")) == 1
    assert len(client.calls_for("spawn_instance")) == 1


def test_upload_files_skips_run_when_nothing_valid(sandbox: ContreeSandbox, client: ContreeClient):
    responses = sandbox.upload_files([("relative.txt", b"data")])

    assert responses[0].error == "invalid_path"
    assert client.calls_for("spawn_instance") == []


def test_download_one_file_rejects_relative_paths(sandbox: ContreeSandbox):
    response = sandbox.download_one_file("relative.txt")

    assert response.error == "invalid_path"
    assert response.content is None


def test_download_one_file_returns_decoded_content(client: ContreeClient, sandbox: ContreeSandbox):
    encoded = base64.b64encode(b"hello world").decode()
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(exit_code=0, stdout=encoded, stderr=""))

    response = sandbox.download_one_file("/data/file.txt")

    assert response.content == b"hello world"
    assert response.error is None


def test_download_one_file_missing_returns_file_not_found(client: ContreeClient, sandbox: ContreeSandbox):
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(exit_code=1, stdout="", stderr=""))

    response = sandbox.download_one_file("/data/missing.txt")

    assert response.error == "file_not_found"
    assert response.content is None


def test_download_files_downloads_each_path(client: ContreeClient, sandbox: ContreeSandbox):
    encoded = base64.b64encode(b"data").decode()
    client.mock("spawn_instance", spawn_response())
    client.mock("wait_operation", operation_response(exit_code=0, stdout=encoded, stderr=""))

    responses = sandbox.download_files(["/a.txt", "/b.txt"])

    assert [r.path for r in responses] == ["/a.txt", "/b.txt"]
    assert all(r.content == b"data" for r in responses)
