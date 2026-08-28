from datetime import timedelta
from uuid import UUID

import pytest


pytest.importorskip("deepagents", reason="langchain integration needs deepagents (Python >= 3.11)")

from contree_client.exceptions import NotFoundError, UnprocessableEntityError
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk.langchain.sandbox import ContreeSandbox, ContreeSandboxAsync, ContreeSandboxSync, to_execute_response
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.sdk.objects.image_like.result import ContreeResult
from contree_sdk.sdk.objects.session import ContreeSession, ContreeSessionSync
from tests.unit.fixtures.files import queue_upload
from tests.unit.fixtures.operations import queue_run


@pytest.fixture
def fake_session(fake_image: ContreeImage) -> ContreeSession:
    return fake_image.session()


@pytest.fixture
def fake_session_s(fake_image_s: ContreeImageSync) -> ContreeSessionSync:
    return fake_image_s.session()


def test_to_execute_response_skips_none_stream():
    result = ContreeResult(
        stdout=None,
        stderr="err\n",
        exit_code=1,
        elapsed_time=timedelta(seconds=1),
        truncated={},
        cost=None,
        raw=None,
    )

    response = to_execute_response(result)

    assert response.output == "err\n"
    assert response.exit_code == 1


def test_dispatches_to_async_for_async_session(fake_session: ContreeSession):
    sandbox = ContreeSandbox(fake_session)
    assert isinstance(sandbox, ContreeSandboxAsync)
    assert sandbox.id.startswith("contree-")
    assert sandbox.id.endswith(f"-from-{fake_session.uuid}")


def test_dispatches_to_sync_for_sync_session(fake_session_s: ContreeSessionSync):
    sandbox = ContreeSandbox(fake_session_s)
    assert isinstance(sandbox, ContreeSandboxSync)
    assert sandbox.id.endswith(f"-from-{fake_session_s.uuid}")


async def test_async_sandbox_rejects_sync_calls(fake_session: ContreeSession):
    sandbox = ContreeSandbox(fake_session)
    with pytest.raises(NotImplementedError):
        sandbox.execute("true")
    with pytest.raises(NotImplementedError):
        sandbox.upload_files([])
    with pytest.raises(NotImplementedError):
        sandbox.download_files([])


async def test_sync_sandbox_rejects_async_calls(fake_session_s: ContreeSessionSync):
    sandbox = ContreeSandbox(fake_session_s)
    with pytest.raises(NotImplementedError):
        await sandbox.aexecute("true")
    with pytest.raises(NotImplementedError):
        await sandbox.aupload_files([])
    with pytest.raises(NotImplementedError):
        await sandbox.adownload_files([])


async def test_upload_files_valid_path(
    fake_session: ContreeSession,
    fake_api: ContreeAsyncClient,
    file_uuid: str,
    file_sha256: str,
    result_image_uuid: UUID,
):
    queue_upload(fake_api, file_uuid, file_sha256)
    queue_run(fake_api, result_image_uuid=str(result_image_uuid))
    sandbox = ContreeSandbox(fake_session)

    [response] = await sandbox.aupload_files([("/app/data.txt", b"content")])

    assert response.path == "/app/data.txt"
    assert response.error is None


async def test_upload_files_rejects_relative_path(fake_session: ContreeSession, fake_api: ContreeAsyncClient):
    sandbox = ContreeSandbox(fake_session)

    [response] = await sandbox.aupload_files([("relative/path.txt", b"content")])

    assert response.path == "relative/path.txt"
    assert response.error == "invalid_path"
    assert not fake_api.calls_for("ensure_file")


async def test_upload_files_mixed_paths(
    fake_session: ContreeSession,
    fake_api: ContreeAsyncClient,
    file_uuid: str,
    file_sha256: str,
    result_image_uuid: UUID,
):
    queue_upload(fake_api, file_uuid, file_sha256)
    queue_run(fake_api, result_image_uuid=str(result_image_uuid))
    sandbox = ContreeSandbox(fake_session)

    responses = await sandbox.aupload_files([("/app/data.txt", b"content"), ("relative.txt", b"other")])

    by_path = {response.path: response.error for response in responses}
    assert by_path == {"/app/data.txt": None, "relative.txt": "invalid_path"}


def test_upload_files_sync(
    fake_session_s: ContreeSessionSync,
    fake_api_s: ContreeClient,
    file_uuid: str,
    file_sha256: str,
    result_image_uuid: UUID,
):
    queue_upload(fake_api_s, file_uuid, file_sha256)
    queue_run(fake_api_s, result_image_uuid=str(result_image_uuid))
    sandbox = ContreeSandbox(fake_session_s)

    [response] = sandbox.upload_files([("/app/data.txt", b"content")])

    assert response.error is None


async def test_download_file_found(fake_session: ContreeSession, fake_api: ContreeAsyncClient):
    fake_api.mock("inspect_image_download", b"file content")
    sandbox = ContreeSandbox(fake_session)

    [response] = await sandbox.adownload_files(["/app/data.txt"])

    assert response.path == "/app/data.txt"
    assert response.content == b"file content"
    assert response.error is None


async def test_download_file_not_found(fake_session: ContreeSession, fake_api: ContreeAsyncClient):
    fake_api.mock("inspect_image_download", error=NotFoundError(404, "file not found"))
    sandbox = ContreeSandbox(fake_session)

    [response] = await sandbox.adownload_files(["/app/missing.txt"])

    assert response.content is None
    assert response.error == "file_not_found"


async def test_download_file_unprocessable_path(fake_session: ContreeSession, fake_api: ContreeAsyncClient):
    fake_api.mock("inspect_image_download", error=UnprocessableEntityError(422, "not a regular file"))
    sandbox = ContreeSandbox(fake_session)

    [response] = await sandbox.adownload_files(["/app/adir"])

    assert response.content is None
    assert response.error == "invalid_path"


async def test_download_file_rejects_relative_path(fake_session: ContreeSession, fake_api: ContreeAsyncClient):
    sandbox = ContreeSandbox(fake_session)

    [response] = await sandbox.adownload_files(["relative.txt"])

    assert response.error == "invalid_path"
    assert not fake_api.calls_for("inspect_image_download")


def test_download_files_sync(fake_session_s: ContreeSessionSync, fake_api_s: ContreeClient):
    fake_api_s.mock("inspect_image_download", b"file content")
    sandbox = ContreeSandbox(fake_session_s)

    [response] = sandbox.download_files(["/app/data.txt"])

    assert response.content == b"file content"


def test_download_file_not_found_s(fake_session_s: ContreeSessionSync, fake_api_s: ContreeClient):
    fake_api_s.mock("inspect_image_download", error=NotFoundError(404, "file not found"))
    sandbox = ContreeSandbox(fake_session_s)

    [response] = sandbox.download_files(["/app/missing.txt"])

    assert response.content is None
    assert response.error == "file_not_found"


def test_download_file_unprocessable_path_s(fake_session_s: ContreeSessionSync, fake_api_s: ContreeClient):
    fake_api_s.mock("inspect_image_download", error=UnprocessableEntityError(422, "not a regular file"))
    sandbox = ContreeSandbox(fake_session_s)

    [response] = sandbox.download_files(["/app/adir"])

    assert response.content is None
    assert response.error == "invalid_path"


def test_download_file_rejects_relative_path_s(fake_session_s: ContreeSessionSync, fake_api_s: ContreeClient):
    sandbox = ContreeSandbox(fake_session_s)

    [response] = sandbox.download_files(["relative.txt"])

    assert response.error == "invalid_path"
    assert not fake_api_s.calls_for("inspect_image_download")


async def test_execute_combines_stdout_and_stderr(
    fake_session: ContreeSession, fake_api: ContreeAsyncClient, result_image_uuid: UUID
):
    queue_run(fake_api, stdout="out\n", stderr="err\n", result_image_uuid=str(result_image_uuid))
    sandbox = ContreeSandbox(fake_session)

    response = await sandbox.aexecute("echo hi")

    assert response.output == "out\nerr\n"
    assert response.exit_code == 0
    assert response.truncated is False


def test_execute_sync(fake_session_s: ContreeSessionSync, fake_api_s: ContreeClient, result_image_uuid: UUID):
    queue_run(fake_api_s, stdout="hi\n", result_image_uuid=str(result_image_uuid))
    sandbox = ContreeSandbox(fake_session_s)

    response = sandbox.execute("echo hi")

    assert response.output == "hi\n"
    assert response.exit_code == 0


def test_import_without_deepagents_raises_clear_error(monkeypatch: pytest.MonkeyPatch):
    import sys

    monkeypatch.delitem(sys.modules, "contree_sdk.langchain.sandbox", raising=False)
    for name in ("deepagents", "deepagents.backends.protocol", "deepagents.backends.sandbox"):
        monkeypatch.setitem(sys.modules, name, None)

    with pytest.raises(ImportError, match="langchain"):
        import contree_sdk.langchain.sandbox  # noqa: F401
