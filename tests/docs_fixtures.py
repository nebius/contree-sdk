"""Offline API outcomes for scenarios executed directly from Markdown."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from contree_client.models import (
    DirectoryList,
    EventDataStream,
    FileResponse,
    InstanceResult,
    InstanceResultState,
    InstanceSpawnResponse,
    OperationEvent,
    OperationInstanceMetadata,
    OperationResponse,
    OperationStatus,
    StreamRepr,
)
from contree_client.testing import ContreeAsyncClient, ContreeClient


class DocumentationAPI:
    """Keep SDK orchestration real and supply explicit remote responses per scenario."""

    def __init__(self) -> None:
        self.sync = ContreeClient()
        self.async_client = ContreeAsyncClient()
        self.sequence = 0
        self.stage_copy = False
        for client in (self.sync, self.async_client):
            client.mock("resolve_image", "base-image")
            client.mock("check_image_archive", True)
            client.mock("check_file_exists", True)
            client.mock("ensure_file", FileResponse(uuid="uploaded-file", sha256="a" * 64, size=4))
            client.mock("cancel_operation", None)
            client.mock("operation_subprocess_kill", None)
            client.mock("operation_subprocess_stdin", None)

    def complete(
        self,
        *,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        wait_for: int | None = None,
        status: OperationStatus = OperationStatus.SUCCESS,
        stream: bool = True,
    ) -> None:
        self.sequence += 1
        operation_uuid = f"operation-{self.sequence}"
        response = OperationResponse(
            uuid=f"operation-{wait_for or self.sequence}",
            kind="instance",
            status=status,
            result_image_uuid=f"image-{wait_for or self.sequence}",
            metadata=OperationInstanceMetadata(
                image="base-image",
                command="documentation command",
                result=InstanceResult(
                    state=InstanceResultState(exit_code=exit_code),
                    stdout=StreamRepr.from_text(stdout),
                    stderr=StreamRepr.from_text(stderr),
                ),
            ),
        )
        for client in (self.sync, self.async_client):
            client.mock("spawn_instance", InstanceSpawnResponse(uuid=operation_uuid))
            client.mock("wait_operation", response)
            if not (stream and self.stage_copy):
                client.mock("get_operation_status", response)
            if stream:
                if self.stage_copy:
                    from tests.unit.docker.copy_clients import mock_copy_completion

                    mock_copy_completion(client, response)
                else:
                    client.mock(
                        "follow_operation_events",
                        [OperationEvent(id=1, ts=datetime.now(timezone.utc), type="completion", data={})],
                    )

    def download(self, data: bytes) -> None:
        for client in (self.sync, self.async_client):
            client.mock("inspect_image_download", data)
            client.mock("inspect_instance_download", data)

    def command(self, stdout: str = "", exit_code: int = 0) -> None:
        """Set the response returned for commands in a shared sandbox."""
        self.command_result = InstanceResult(
            state=InstanceResultState(exit_code=exit_code), stdout=StreamRepr.from_text(stdout)
        )

    def subprocess(self, stdout: str = "Hello from a subprocess!\n") -> None:
        self.complete(stream=False)
        events = [
            OperationEvent(
                id=1,
                ts=datetime.now(timezone.utc),
                type="stdout",
                spid=2,
                data=EventDataStream(value=stdout, encoding="ascii"),
            ),
            OperationEvent(id=2, ts=datetime.now(timezone.utc), type="exit", spid=2, data={}),
            OperationEvent(id=3, ts=datetime.now(timezone.utc), type="completion", data={}),
        ]
        for client in (self.sync, self.async_client):
            client.mock("follow_operation_events", events)
            client.mock("operation_subprocess_create", 2)
            client.mock(
                "operation_subprocess",
                InstanceResult(state=InstanceResultState(exit_code=0), stdout=StreamRepr.from_text(stdout)),
            )


@pytest.fixture
def doc_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> DocumentationAPI:
    api = DocumentationAPI()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("CONTREE_TOKEN", "documentation-token")
    monkeypatch.setenv("CONTREE_URL", "https://contree.invalid")
    monkeypatch.setenv("CONTREE_IMAGE", "tag:tutorial-base")
    monkeypatch.setenv("CONTREE_PROJECT", "documentation-project")
    for path, client in [
        ("contree_client.sync.ContreeClient", api.sync),
        ("contree_client.asyncio.ContreeAsyncClient", api.async_client),
        ("contree_client.httpx.ContreeClient", api.sync),
        ("contree_client.aiohttp.ContreeAsyncClient", api.async_client),
    ]:
        factory = Mock(return_value=client)
        factory.from_profile = Mock(return_value=client)
        monkeypatch.setattr(path, factory)
    return api


@pytest.fixture
def deepagents_available() -> None:
    pytest.importorskip("deepagents")


@pytest.fixture
def agent_model_factory() -> type:
    """Replace only model responses; retain real framework tools and orchestration."""
    pytest.importorskip("deepagents")
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel

    from contree_sdk.compat import Self

    class ScriptedModel(FakeMessagesListChatModel):
        def bind_tools(self, tools: object, **kwargs: object) -> Self:
            return self

    return ScriptedModel


@pytest.fixture
def doc_build_context(doc_api: DocumentationAPI, tmp_path: Path) -> None:
    """Use the build guide context for its own examples and advanced scenarios."""
    import re

    guide = Path(__file__).resolve().parents[1] / "docs/python_sdk/building-images.md"
    source = guide.read_text()
    context = tmp_path / "build-context"
    context.mkdir()
    for language, filename in [("dockerfile", "Dockerfile"), ("text", "message.txt")]:
        match = re.search(rf"```{language}\n(.*?)\n```", source, re.DOTALL)
        if match is None:
            raise ValueError(f"missing {language} block in {guide}")
        (context / filename).write_text(match[1] + "\n")


@pytest.fixture
def doc_stage_file(doc_api: DocumentationAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide stage-file bytes and metadata; the example creates its local context."""
    import hashlib
    from typing import IO

    from tests.unit.docker.copy_clients import source_item

    def ensure_file(content: IO[bytes], **kwargs: object) -> FileResponse:
        data = content.read()
        sha256 = hashlib.sha256(data).hexdigest()
        return FileResponse(uuid=sha256, sha256=sha256, size=len(data))

    async def ensure_file_async(content: IO[bytes], **kwargs: object) -> FileResponse:
        return ensure_file(content, **kwargs)

    for client in (doc_api.sync, doc_api.async_client):
        client.mock("inspect_image_list", DirectoryList(path="/", files=[source_item("built.txt")]))
        client.mock("inspect_image_download_stream", [b"one\n"])
        client.mock("inspect_image_download_stream", [b"two\n"])
    monkeypatch.setattr(doc_api.sync, "ensure_file", ensure_file)
    monkeypatch.setattr(doc_api.async_client, "ensure_file", ensure_file_async)


@pytest.fixture
def lazy_api(doc_api: DocumentationAPI, monkeypatch: pytest.MonkeyPatch) -> DocumentationAPI:
    """Supply a controllable live transport; retain the real SDK lifecycle."""
    from tests.unit.session.lazy_clients import LiveAsyncClient, LiveClient

    doc_api.sync = LiveClient()
    doc_api.async_client = LiveAsyncClient()
    for client in (doc_api.sync, doc_api.async_client):
        client.mock("ensure_file", FileResponse(uuid="uploaded-file", sha256="a" * 64, size=4))
        client.mock("operation_subprocess_stdin", None)
        client.mock("apply_instance_file", None)
    for path, client in [
        ("contree_client.sync.ContreeClient", doc_api.sync),
        ("contree_client.asyncio.ContreeAsyncClient", doc_api.async_client),
        ("contree_client.httpx.ContreeClient", doc_api.sync),
        ("contree_client.aiohttp.ContreeAsyncClient", doc_api.async_client),
    ]:
        factory = Mock(return_value=client)
        factory.from_profile = Mock(return_value=client)
        monkeypatch.setattr(path, factory)
    return doc_api


@pytest.fixture
def sandbox_api(lazy_api: DocumentationAPI, monkeypatch: pytest.MonkeyPatch) -> DocumentationAPI:
    """Replace factory transports while retaining profile resolution and SDK lifecycle."""
    lazy_api.command("Hello from ConTree!\n")

    def result(operation_id: str, spid: int) -> InstanceResult:
        return lazy_api.command_result

    async def async_result(operation_id: str, spid: int) -> InstanceResult:
        return result(operation_id, spid)

    monkeypatch.setattr(lazy_api.sync, "operation_subprocess", result)
    monkeypatch.setattr(lazy_api.async_client, "operation_subprocess", async_result)
    return lazy_api


@pytest.fixture
def stdin_api(doc_api: DocumentationAPI, monkeypatch: pytest.MonkeyPatch) -> DocumentationAPI:
    """Deliver input to a controlled live process and emit completion after EOF."""
    from tests.unit.session.stdin_clients import AsyncStdinClient, StdinClient

    doc_api.sync = StdinClient()
    doc_api.async_client = AsyncStdinClient()
    for path, client in [
        ("contree_client.sync.ContreeClient", doc_api.sync),
        ("contree_client.asyncio.ContreeAsyncClient", doc_api.async_client),
        ("contree_client.httpx.ContreeClient", doc_api.sync),
        ("contree_client.aiohttp.ContreeAsyncClient", doc_api.async_client),
    ]:
        factory = Mock(return_value=client)
        factory.from_profile = Mock(return_value=client)
        monkeypatch.setattr(path, factory)
    return doc_api
