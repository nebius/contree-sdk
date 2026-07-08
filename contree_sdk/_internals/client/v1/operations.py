import json
from uuid import UUID

from contree_sdk._internals.lib.api_decorator import delete, get
from contree_sdk._internals.lib.client_base import ClientBase
from contree_sdk._internals.lib.helpers import convert_data_to_type
from contree_sdk._internals.models.operation import OperationEvent, OperationModel


class OperationsMixin:
    @get("/v1/operations/{operation_id}", json=True)
    async def get_operation_status(self, operation_id: str | UUID) -> OperationModel: ...

    @delete("/v1/operations/{operation_id}")
    async def cancel_operation(self, operation_id: str | UUID) -> None: ...

    async def stream_operation_events(self: ClientBase, operation_id: str | UUID, follow: bool = True, since: int = -1):
        async with self._client.stream(
            "GET",
            f"/v1/operations/{operation_id}/events",
            params={
                "follow": int(follow),
                "since": int(since),
            },
        ) as response:
            data = {}
            async for line in response.aiter_lines():
                if not line.strip():
                    yield convert_data_to_type(json.loads(data["data"]), OperationEvent)
                    data = {}
                    continue
                name, value = line.split(":", 1)
                value = value.strip()
                data[name] = value
