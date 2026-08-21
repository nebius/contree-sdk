from pathlib import Path

import pytest
from contree_client.models import (
    FileResponse,
    InstanceResult,
    InstanceResultState,
    InstanceSpawnResponse,
    OperationInstanceMetadata,
    OperationResponse,
    OperationStatus,
    StreamRepr,
)
from contree_client.testing import ContreeAsyncClient as MockAsyncClient
from contree_client.testing import ContreeClient as MockSyncClient

from contree_sdk.store import SQLiteStore


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool:
    return "_tmp" in str(collection_path)


def operation_response(
    *,
    operation_uuid: str = "op-1",
    image_uuid: str = "image-uuid",
    result_image_uuid: str = "image-uuid-next",
    command: str = "",
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> OperationResponse:
    return OperationResponse(
        uuid=operation_uuid,
        kind="instance",
        status=OperationStatus.SUCCESS,
        error=None,
        result_image_uuid=result_image_uuid,
        metadata=OperationInstanceMetadata(
            command=command,
            image=image_uuid,
            result=InstanceResult(
                state=InstanceResultState(exit_code=exit_code),
                stdout=StreamRepr(value=stdout, encoding="ascii"),
                stderr=StreamRepr(value=stderr, encoding="ascii"),
            ),
        ),
    )


@pytest.fixture
def api_fake_quick_start_sync(monkeypatch: pytest.MonkeyPatch):
    client = MockSyncClient()
    client.mock("resolve_image", "python-uuid")
    client.mock("spawn_instance", InstanceSpawnResponse(uuid="op-1"))
    client.mock("wait_operation", operation_response(stdout="Hello from Contree!\n"))
    monkeypatch.setattr("contree_client.sync.ContreeClient", lambda *args, **kwargs: client)


@pytest.fixture
def api_fake_quick_start_async(monkeypatch: pytest.MonkeyPatch):
    client = MockAsyncClient()
    client.mock("resolve_image", "python-uuid")
    client.mock("spawn_instance", InstanceSpawnResponse(uuid="op-1"))
    client.mock("wait_operation", operation_response(stdout="Hello from Contree!\n"))
    monkeypatch.setattr("contree_client.asyncio.ContreeAsyncClient", lambda *args, **kwargs: client)


@pytest.fixture
def api_fake_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    client = MockSyncClient()
    client.mock("resolve_image", "python-uuid")
    client.mock("spawn_instance", InstanceSpawnResponse(uuid="op-1"))
    client.mock("wait_operation", operation_response(exit_code=0))
    monkeypatch.setattr("contree_client.sync.ContreeClient", lambda *args, **kwargs: client)

    db_path = tmp_path / "contree-example.db"
    monkeypatch.setattr("contree_sdk.store.SQLiteStore", lambda *args, **kwargs: SQLiteStore(db_path))


@pytest.fixture
def api_fake_branching(monkeypatch: pytest.MonkeyPatch):
    client = MockSyncClient()
    client.mock("resolve_image", "python-uuid")
    client.mock("spawn_instance", InstanceSpawnResponse(uuid="op-1"))
    client.mock("wait_operation", operation_response(exit_code=0))
    monkeypatch.setattr("contree_client.sync.ContreeClient", lambda *args, **kwargs: client)


@pytest.fixture
def api_fake_resume(monkeypatch: pytest.MonkeyPatch):
    client = MockSyncClient()
    client.mock("resolve_image", "python-uuid")
    client.mock("spawn_instance", InstanceSpawnResponse(uuid="op-1"))
    client.mock("wait_operation", operation_response(exit_code=0))
    monkeypatch.setattr("contree_client.sync.ContreeClient", lambda *args, **kwargs: client)


@pytest.fixture
def api_fake_file_upload(monkeypatch: pytest.MonkeyPatch):
    client = MockSyncClient()
    client.mock("resolve_image", "python-uuid")
    client.mock("ensure_file", FileResponse(uuid="file-uuid", sha256="a" * 64, size=17))
    client.mock("spawn_instance", InstanceSpawnResponse(uuid="op-1"))
    client.mock("wait_operation", operation_response(stdout="#!/bin/sh\necho hello\n"))
    monkeypatch.setattr("contree_client.sync.ContreeClient", lambda *args, **kwargs: client)
