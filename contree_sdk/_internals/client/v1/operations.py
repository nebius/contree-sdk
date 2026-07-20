import json
from collections.abc import AsyncGenerator
from contextlib import aclosing
from uuid import UUID

from cattrs.errors import BaseValidationError

from contree_sdk._internals.lib.api_decorator import delete
from contree_sdk._internals.lib.client_base import ClientBase
from contree_sdk._internals.lib.helpers import convert_data_to_type
from contree_sdk._internals.models.operation import OperationEvent
from contree_sdk._internals.utils.exception import wrap_api_call
from contree_sdk.sdk.exceptions.api import EventStreamInterruptedError, MalformedEventError, MalformedStreamEventError


_FINAL_EVENT_TYPES = frozenset({"completion", "exit"})


class OperationsMixin:
    @delete("/v1/operations/{operation_id}")
    async def cancel_operation(self, operation_id: str | UUID) -> None: ...

    async def stream_operation_events(
        self: ClientBase, operation_id: str | UUID, follow: bool = True, since: int = -1
    ) -> AsyncGenerator[OperationEvent]:
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
            if response.is_error:
                await response.aread()
            response.raise_for_status()
            async with aclosing(response) as response:
                async for line in response.aiter_lines():
                    if line.startswith(":"):
                        continue
                    if not line.strip():
                        if not data:
                            continue
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
    if data.get("event") == "sse_error":
        raise EventStreamInterruptedError(error=data.get("data"))

    event_type = data.get("event")
    error_class = MalformedEventError
    if event_type is not None and event_type not in _FINAL_EVENT_TYPES:
        error_class = MalformedStreamEventError

    if "data" not in data:
        raise error_class(
            data=data,
            error="No data in event",
        )

    try:
        return convert_data_to_type(json.loads(data["data"]), OperationEvent)
    except (TypeError, ValueError, BaseValidationError) as e:
        raise error_class(
            data=data,
            error=str(e),
        ) from e
