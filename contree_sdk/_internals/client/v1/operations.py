import json
from contextlib import aclosing
from uuid import UUID

from contree_sdk._internals.lib.api_decorator import delete, get
from contree_sdk._internals.lib.client_base import ClientBase
from contree_sdk._internals.lib.helpers import convert_data_to_type
from contree_sdk._internals.models.operation import OperationEvent, OperationModel
from contree_sdk._internals.utils.exception import wrap_api_call
from contree_sdk.sdk.exceptions.api import MalformedEventError


class OperationsMixin:
    @get("/v1/operations/{operation_id}", json=True)
    async def get_operation_status(self, operation_id: str | UUID) -> OperationModel: ...

    @delete("/v1/operations/{operation_id}")
    async def cancel_operation(self, operation_id: str | UUID) -> None: ...

    async def stream_operation_events(self: ClientBase, operation_id: str | UUID, follow: bool = True, since: int = -1):
        request = self._client.build_request(
            "GET",
            f"/v1/operations/{operation_id}/events",
            params={
                "follow": int(follow),
                "since": since,
            },
        )
        with wrap_api_call():
            data = {}
            response = await self._client.send(request, stream=True)
            async with aclosing(response) as response:
                async for line in response.aiter_lines():
                    if not line.strip():
                        yield _stream_data_to_event(data)  # noqa: ASYNC119
                        data = {}
                        continue
                    if ":" not in line:
                        raise MalformedEventError(
                            data=data,
                            error=f"No delimiter in line {line}",
                        )
                    name, value = line.split(":", 1)
                    value = value.strip()
                    data[name] = value
                if data:
                    yield _stream_data_to_event(data)  # noqa: ASYNC119


def _stream_data_to_event(data: dict) -> OperationEvent:
    if "data" not in data:
        raise MalformedEventError(
            data=data,
            error="No data in event",
        )

    try:
        return convert_data_to_type(json.loads(data["data"]), OperationEvent)
    except (TypeError, ValueError) as e:
        raise MalformedEventError(
            data=data,
            error=str(e),
        ) from e
