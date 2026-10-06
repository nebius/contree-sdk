"""Offline API outcomes for scenarios executed directly from Markdown."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
from contree_client.models import (
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

from tests.unit.session.lazy_clients import LiveAsyncClient


class DocumentationAPI:
    """Keep SDK orchestration real and supply explicit remote responses per scenario."""

    def __init__(self) -> None:
        self.sync = ContreeClient()
        self.async_client = ContreeAsyncClient()
        self.sequence = 0
        for client in (self.sync, self.async_client):
            client.mock("resolve_image", "base-image")
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
            client.mock("get_operation_status", response)
            if stream:
                client.mock(
                    "follow_operation_events",
                    [OperationEvent(id=1, ts=datetime.now(timezone.utc), type="completion", data={})],
                )

    def download(self, data: bytes) -> None:
        for client in (self.sync, self.async_client):
            client.mock("inspect_image_download", data)

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
    monkeypatch.setenv("CONTREE_TOKEN", "documentation-token")
    monkeypatch.setenv("CONTREE_URL", "https://contree.invalid")
    monkeypatch.setenv("CONTREE_IMAGE", "tag:tutorial-base")
    for path, client in [
        ("contree_client.sync.ContreeClient", api.sync),
        ("contree_client.asyncio.ContreeAsyncClient", api.async_client),
    ]:
        factory = Mock(return_value=client)
        factory.from_profile = Mock(return_value=client)
        monkeypatch.setattr(path, factory)
    return api


@pytest.fixture
def deepagents_available() -> None:
    pytest.importorskip("deepagents")


@pytest.fixture
def doc_build_context(doc_api: DocumentationAPI, request: pytest.FixtureRequest, tmp_path: Path) -> None:
    """Use the files shown on the build page instead of maintaining test copies."""
    import re

    source = request.path.read_text()
    context = tmp_path / "build-context"
    context.mkdir()
    for language, filename in [("dockerfile", "Dockerfile"), ("text", "message.txt")]:
        match = re.search(rf"```{language}\n(.*?)\n```", source, re.DOTALL)
        if match is None:
            raise ValueError(f"missing {language} block in {request.path}")
        (context / filename).write_text(match[1] + "\n")


@pytest.fixture
def lazy_api(doc_api: DocumentationAPI, monkeypatch: pytest.MonkeyPatch) -> DocumentationAPI:
    """Supply a controllable live transport; retain the real SDK lifecycle."""
    from tests.unit.session.lazy_clients import LiveAsyncClient, LiveClient

    doc_api.sync = LiveClient()
    doc_api.async_client = LiveAsyncClient()
    for path, client in [
        ("contree_client.sync.ContreeClient", doc_api.sync),
        ("contree_client.asyncio.ContreeAsyncClient", doc_api.async_client),
    ]:
        factory = Mock(return_value=client)
        factory.from_profile = Mock(return_value=client)
        monkeypatch.setattr(path, factory)
    return doc_api


@pytest.fixture
def stdin_api(doc_api: DocumentationAPI, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> DocumentationAPI:
    """Deliver input to a controlled live process and emit completion after EOF."""
    from tests.unit.session.stdin_clients import AsyncStdinClient, StdinClient

    (tmp_path / "input.bin").write_bytes(bytes(range(256)) * 1024)
    doc_api.sync = StdinClient()
    doc_api.async_client = AsyncStdinClient()
    for path, client in [
        ("contree_client.sync.ContreeClient", doc_api.sync),
        ("contree_client.asyncio.ContreeAsyncClient", doc_api.async_client),
    ]:
        factory = Mock(return_value=client)
        factory.from_profile = Mock(return_value=client)
        monkeypatch.setattr(path, factory)
    return doc_api


@pytest.fixture
def doc_runtime_client(monkeypatch: pytest.MonkeyPatch) -> LiveAsyncClient:
    """Drive a real runtime with a controllable single operation stream."""
    client = LiveAsyncClient()
    factory = Mock(return_value=client)
    factory.from_profile = Mock(return_value=client)
    monkeypatch.setattr("contree_client.asyncio.ContreeAsyncClient", factory)
    return client
