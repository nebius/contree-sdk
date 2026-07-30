from __future__ import annotations

import asyncio
import dataclasses
from asyncio import Event, Lock, Queue, create_task, gather, shield
from collections import defaultdict
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from sys import version_info
from types import EllipsisType
from typing import TYPE_CHECKING, Literal, TypeVar, overload
from uuid import UUID

from contree_client.models import (
    EventDataCompletion,
    EventDataExit,
    EventDataStream,
    EventDataTruncated,
    OperationEvent,
)

from contree_sdk._internals.io.typing import AsyncWritable, Writable
from contree_sdk._internals.io.writer_wrapper import EOF, WriterToQueue, WriterWrapper
from contree_sdk.sdk.exceptions import (
    CancelledOperationError,
    ContreeApiError,
    EventStreamInterruptedError,
    FailedOperationError,
    GoneError,
    MalformedEventError,
    NotFoundError,
    OperationTimedOutError,
)
from contree_sdk.utils.models.operation import OperationStatus


if version_info >= (3, 11):
    from asyncio import timeout
else:
    from async_timeout import timeout

if TYPE_CHECKING:
    from contree_sdk.sdk.client._base import _ContreeBase


StreamName = Literal["stderr", "stdout"]
EventDataT = TypeVar("EventDataT")


@dataclass
class OutputChunk:
    value: bytes
    stream_name: StreamName


@dataclass
class ProcessView:
    exit: EventDataExit | None
    outputs: dict[StreamName, bytes]
    truncated: dict[str, EventDataTruncated]


MAIN_SPID = 1


def _event_data(
    event: OperationEvent, data_type: type[EventDataT], error_class: type[MalformedEventError]
) -> EventDataT:
    if isinstance(event.data, data_type):
        return event.data
    raise error_class(
        data=event.data if isinstance(event.data, dict) else None,
        error=f"unexpected payload for {event.type} event: {event.data!r}",
    )


def _unset_to_none(value: EventDataT | EllipsisType) -> EventDataT | None:
    return None if isinstance(value, EllipsisType) else value


class OperationWaiter:
    def __init__(self, client: _ContreeBase, operation_id: UUID):
        self.operation_id = operation_id
        self._client = client
        self._output_by_spid = defaultdict(lambda: defaultdict(bytes))
        # IO objects by spid and stream name
        self._readers_by_spid: dict[tuple[int | None, str], list[WriterWrapper]] = defaultdict(list)

        self._finished_event = Event()
        self._streaming_lock = Lock()
        self._processing_lock = Lock()
        self._last_event_id = -1
        self._exits: dict[int | None, EventDataExit] = {}
        self._truncated: dict[int | None, dict[str, EventDataTruncated]] = defaultdict(dict)
        self.completion: EventDataCompletion | None = None

    async def _load_events(self):
        async with self._streaming_lock:
            if self._finished_event.is_set():
                return
            try:
                async for event in self._client._api.iter_operation_events(
                    str(self.operation_id), follow=True, since=self._last_event_id
                ):
                    await self._process_event(event)
            except (NotFoundError, GoneError) as e:
                if self._last_event_id >= 0:
                    raise CancelledOperationError(operation_uuid=self.operation_id) from e
                raise
            if not self._finished_event.is_set():
                raise EventStreamInterruptedError(error="stream ended before completion event")

    async def _process_event(self, event: OperationEvent):
        async with self._processing_lock:
            spid = _unset_to_none(event.spid)
            if event.type in {"stderr", "stdout"}:
                value = _event_data(event, EventDataStream, MalformedEventError).as_bytes()
                self._output_by_spid[spid][event.type] += value
                for reader in self._readers_by_spid[spid, event.type]:
                    await reader.write(value)
            elif event.type == "exit":
                self._exits[spid] = _event_data(event, EventDataExit, MalformedEventError)
            elif event.type == "truncated":
                truncated = _event_data(event, EventDataTruncated, MalformedEventError)
                self._truncated[spid][truncated.stream] = truncated
            elif event.type == "completion":
                completion = _event_data(event, EventDataCompletion, MalformedEventError)
                self.completion = dataclasses.replace(
                    completion,
                    result_image_uuid=_unset_to_none(completion.result_image_uuid),
                    error=_unset_to_none(completion.error),
                )
                await self._finish()

            self._last_event_id = event.id

    async def iter_chunks(self, spid: int):
        queues: dict[StreamName, Queue] = {}
        for key in ("stdout", "stderr"):
            queue = Queue()
            queues[key] = queue
            await self.connect_output(output=WriterToQueue(queue=queue), stream_name=key, spid=spid)
        tasks = {create_task(queue.get()): key for key, queue in queues.items()}

        try:
            while tasks:
                done, _ = await asyncio.wait(
                    tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in done:
                    key = tasks.pop(task)
                    value = task.result()
                    if value is EOF:
                        continue

                    yield OutputChunk(
                        value=value,
                        stream_name=key,
                    )

                    tasks[create_task(queues[key].get())] = key
        finally:
            for task in tasks:
                task.cancel()

            await gather(*tasks, return_exceptions=True)

    async def connect_output(self, *, output: AsyncWritable | Writable, spid: int, stream_name: str):
        wrapper = WriterWrapper(output)

        async with self._processing_lock:
            if self._output_by_spid[spid][stream_name]:
                await wrapper.write(self._output_by_spid[spid][stream_name])
            if self._finished_event.is_set():
                await wrapper.finalize()
                return
            self._readers_by_spid[spid, stream_name].append(wrapper)

    def process_view(self, spid: int = MAIN_SPID) -> ProcessView:
        return ProcessView(
            exit=self._exits.get(spid),
            outputs={name: self._output_by_spid[spid][name] for name in ("stdout", "stderr")},
            truncated=dict(self._truncated[spid]),
        )

    @overload
    async def wait_for_result(
        self, *, operation_timeout: float | None = None, spid: int = MAIN_SPID
    ) -> tuple[EventDataCompletion, EventDataExit]: ...
    @overload
    async def wait_for_result(
        self, *, operation_timeout: float | None = None, spid: None
    ) -> tuple[EventDataCompletion, None]: ...

    async def wait_for_result(
        self, *, operation_timeout: float | None = None, spid: int | None = MAIN_SPID
    ) -> tuple[EventDataCompletion, EventDataExit | None]:
        retrier = self._client._default_retrier
        try:
            async with self._operation_canceller(), timeout(operation_timeout):
                await retrier(self._load_events)
        except (TimeoutError, asyncio.TimeoutError) as e:
            raise OperationTimedOutError(operation_uuid=self.operation_id) from e

        completion = self.completion
        if completion is None or completion.status == OperationStatus.CANCELLED:
            raise CancelledOperationError(operation_uuid=self.operation_id)
        if completion.status == OperationStatus.FAILED:
            raise FailedOperationError(
                operation_uuid=self.operation_id, error=_unset_to_none(completion.error) or "Unknown error"
            )

        exit_event = self._exits.get(spid)
        if spid is not None and exit_event is None:
            raise EventStreamInterruptedError(error=f"no exit event received for spid {spid}")
        if exit_event is not None and exit_event.timed_out:
            raise OperationTimedOutError(operation_uuid=self.operation_id)
        return completion, exit_event

    async def _cancel_operation(self):
        await self._client._api.cancel_operation(str(self.operation_id))

    @asynccontextmanager
    async def _operation_canceller(self):
        try:
            yield
        finally:
            if not self._finished_event.is_set():
                with suppress(ContreeApiError):
                    await shield(self._cancel_operation())
                await self._finish()

    async def _finish(self):
        self._finished_event.set()
        for readers in self._readers_by_spid.values():
            for reader in readers:
                await reader.finalize()
        self._readers_by_spid.clear()
