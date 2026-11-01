"""Transport outcomes for stage copies, including controlled live VM clients."""

from dataclasses import replace

from contree_client.models import (
    FileItem,
    InstanceResult,
    InstanceResultState,
    InstanceSpawnResponse,
    OperationInstanceMetadata,
    OperationResponse,
)
from contree_client.testing import ContreeAsyncClient, ContreeClient

from tests.unit.session.lazy_clients import LiveAsyncClient, LiveClient, event, subprocess_events


def mock_copy_completion(client: ContreeClient | ContreeAsyncClient, response: OperationResponse) -> None:
    client.mock(
        "follow_operation_events",
        [
            event("spawn"),
            *subprocess_events(2, InstanceResult(state=InstanceResultState(exit_code=0))),
            event("completion"),
        ],
    )
    client.mock("get_operation_status", response)
    client.mock("apply_instance_file", None)
    client.mock("operation_subprocess_create", 2)
    client.mock("operation_subprocess_kill", None)


def stopped_response(response: OperationResponse) -> OperationResponse:
    return replace(
        response,
        metadata=OperationInstanceMetadata(
            command="sleep", image="base", result=InstanceResult(state=InstanceResultState(exit_code=143))
        ),
    )


class CopyClient(LiveClient):
    def __init__(self):
        super().__init__()
        self.sleep_operations = set()

    def spawn_instance(self, command: str, image: str, **kwargs) -> InstanceSpawnResponse:
        response = super().spawn_instance(command, image, **kwargs)
        self.streams[response.uuid].put(event("spawn"))
        if command == "sleep":
            self.sleep_operations.add(response.uuid)
        else:
            self.streams[response.uuid].put(event("completion"))
        return response

    def get_operation_status(self, operation_id: str, **kwargs) -> OperationResponse:
        response = super().get_operation_status(operation_id, **kwargs)
        return stopped_response(response) if operation_id in self.sleep_operations else response


class CopyAsyncClient(LiveAsyncClient):
    def __init__(self):
        super().__init__()
        self.sleep_operations = set()

    async def spawn_instance(self, command: str, image: str, **kwargs) -> InstanceSpawnResponse:
        response = await super().spawn_instance(command, image, **kwargs)
        await self.streams[response.uuid].put(event("spawn"))
        if command == "sleep":
            self.sleep_operations.add(response.uuid)
        else:
            await self.streams[response.uuid].put(event("completion"))
        return response

    async def get_operation_status(self, operation_id: str, **kwargs) -> OperationResponse:
        response = await super().get_operation_status(operation_id, **kwargs)
        return stopped_response(response) if operation_id in self.sleep_operations else response


def source_item(path: str, *, is_dir: bool = False, mode: int = 0o751, uid: int = 1234, gid: int = 2345) -> FileItem:
    return FileItem(
        size=4,
        path=path,
        owner=uid,
        group=gid,
        uid=uid,
        gid=gid,
        mode=mode,
        mtime=0,
        nlink=1,
        is_dir=is_dir,
        is_regular=not is_dir,
        is_symlink=False,
        is_socket=False,
        is_fifo=False,
        symlink_to="",
    )
