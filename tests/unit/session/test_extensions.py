from dataclasses import replace
from io import BytesIO
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from contree_client.models import FileSpec, InstanceResult, InstanceSpawnResponse, OperationInstanceMetadata, StreamRepr
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk import ContreeAsyncSession, ContreeSession, OperationContext, RunRequest
from contree_sdk.files import AsyncFileTransfer, SyncFileTransfer
from contree_sdk.session import AsyncOperation, AsyncOperationContract, OperationContract
from contree_sdk.store import AsyncMemoryStore, SyncMemoryStore
from tests.unit.session.factories import mock_completion, operation_response, spawn_response


def sync_client():
    client = ContreeClient()
    client.mock("resolve_image", "base")
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response())
    return client


def async_client():
    client = ContreeAsyncClient()
    client.mock("resolve_image", "base")
    client.mock("spawn_instance", spawn_response())
    mock_completion(client, operation_response())
    return client


def test_request_snapshots_args_and_env():
    env = {"KEY": "original"}
    request = RunRequest(command="echo", env=env)
    env["KEY"] = "changed"
    assert request.env == {"KEY": "original"}
    with pytest.raises(TypeError):
        cast("dict[str, str]", request.env)["KEY"] = "changed"


class AsyncPolicySession(ContreeAsyncSession):
    def prepare_request(self, request: RunRequest) -> RunRequest:
        return replace(super().prepare_request(request), disposable=False, cwd="/work")

    def create_operation(self, response: InstanceSpawnResponse, context: OperationContext) -> AsyncOperationContract:
        assert isinstance(response.uuid, str)
        return CustomAsyncOperation(self.client, response.uuid, context=context)


class CustomAsyncOperation(AsyncOperation):
    pass


async def test_async_policy_changes_effective_history_semantics():
    client = async_client()
    session = AsyncPolicySession(client, image="base")
    operation = await session.spawn("echo")
    assert isinstance(operation, CustomAsyncOperation)
    result = await session.execute(RunRequest(command="echo"))
    assert isinstance(result, InstanceResult)
    entries, _ = await session.history()
    assert len(entries) == 2
    assert client.calls_for("spawn_instance")[-1].kwargs["cwd"] == "/work"


class CustomFiles(SyncFileTransfer):
    def upload(self, file):
        return FileSpec(uuid="custom-file", uid=file.uid, gid=file.gid, mode=file.mode)

    def read_file(self, image_uuid, path):
        return f"{image_uuid}:{path}".encode()


class CustomAsyncFiles(AsyncFileTransfer):
    async def upload(self, file):
        return FileSpec(uuid="custom-file", uid=file.uid, gid=file.gid, mode=file.mode)

    async def read_file(self, image_uuid, path):
        return f"{image_uuid}:{path}".encode()


def test_file_component_is_used_for_all_io():
    client = sync_client()
    session = ContreeSession(client, image="base", file_transfer=CustomFiles())
    session.run("cat", files={"/data": b"data"}, stdin=BytesIO(b"input"))
    call = client.calls_for("spawn_instance")[0]
    assert call.kwargs["files"]["/data"].uuid == "custom-file"
    assert StreamRepr(value=call.kwargs["stdin"].value, encoding=call.kwargs["stdin"].encoding).as_bytes() == b"input"
    assert session.read_file("/data") == b"base:/data"
    assert client.calls_for("ensure_file") == []


async def test_async_file_component_is_used_for_all_io():
    client = async_client()
    session = ContreeAsyncSession(client, image="base", file_transfer=CustomAsyncFiles())
    await session.run("cat", files={"/data": b"data"}, stdin=BytesIO(b"input"))
    call = client.calls_for("spawn_instance")[0]
    assert call.kwargs["files"]["/data"].uuid == "custom-file"
    assert StreamRepr(value=call.kwargs["stdin"].value, encoding=call.kwargs["stdin"].encoding).as_bytes() == b"input"
    assert await session.read_file("/data") == b"base:/data"
    assert client.calls_for("ensure_file") == []


class EmptyStore(SyncMemoryStore):
    def __bool__(self):
        return False


class EmptyAsyncStore(AsyncMemoryStore):
    def __bool__(self):
        return False


def test_falsey_store_is_not_replaced():
    store = EmptyStore()
    session = ContreeSession(sync_client(), image="base", store=store)
    assert session.store is store


async def test_falsey_async_store_is_not_replaced():
    store = EmptyAsyncStore()
    session = ContreeAsyncSession(async_client(), image="base", store=store)
    await session.ensure_ready()
    assert session.store is store


class BrokenFactory(ContreeSession):
    def create_operation(self, response: InstanceSpawnResponse, context: OperationContext) -> OperationContract:
        raise ValueError("factory failed")


class BrokenAsyncFactory(ContreeAsyncSession):
    def create_operation(self, response: InstanceSpawnResponse, context: OperationContext) -> AsyncOperationContract:
        raise ValueError("factory failed")


def test_factory_failure_cancels_the_spawned_instance():
    client = sync_client()
    client.mock("cancel_operation", error=OSError("cleanup failed"))
    with pytest.raises(ValueError, match="factory failed"):
        BrokenFactory(client, image="base").run("echo")
    assert client.calls_for("cancel_operation")[0].args == ("op-1",)


async def test_async_factory_failure_cancels_the_spawned_instance():
    client = async_client()
    client.mock("cancel_operation", None)
    with pytest.raises(ValueError, match="factory failed"):
        await BrokenAsyncFactory(client, image="base").run("echo")
    assert client.calls_for("cancel_operation")[0].args == ("op-1",)


def contract_operation(contract, *, asynchronous=False):
    # Reject access to attributes outside the documented lifecycle contract.
    operation = MagicMock(spec_set=[*contract.__abstractmethods__, "uuid", "context", "response"])
    operation.uuid = "op-1"
    operation.response = operation_response()
    assert isinstance(operation.response.metadata, OperationInstanceMetadata)
    result = operation.response.metadata.result
    operation.wait = AsyncMock(return_value=result) if asynchronous else MagicMock(return_value=result)
    operation.shutdown = AsyncMock() if asynchronous else MagicMock()
    return operation


def test_session_commits_using_only_the_operation_contract(monkeypatch):
    client = sync_client()
    session = ContreeSession(client, image="base")
    operation = contract_operation(OperationContract)
    monkeypatch.setattr(session, "create_operation", lambda response, context: operation)
    result = session.run("echo", disposable=False)
    entries, _ = session.history()
    assert entries[-1].operation_uuid == operation.uuid
    assert entries[-1].parent_id == operation.context.parent_id
    assert session.image_uuid == "img-uuid-1"
    assert result is operation.response.metadata.result
    assert client.calls_for("wait_operation") == []
    operation.shutdown.assert_called_once_with()


async def test_async_session_commits_using_only_the_operation_contract(monkeypatch):
    client = async_client()
    session = ContreeAsyncSession(client, image="base")
    operation = contract_operation(AsyncOperationContract, asynchronous=True)
    monkeypatch.setattr(session, "create_operation", lambda response, context: operation)
    result = await session.run("echo", disposable=False)
    entries, _ = await session.history()
    assert entries[-1].operation_uuid == operation.uuid
    assert entries[-1].parent_id == operation.context.parent_id
    assert session.image_uuid == "img-uuid-1"
    assert result is operation.response.metadata.result
    assert client.calls_for("wait_operation") == []
    operation.shutdown.assert_awaited_once_with()
