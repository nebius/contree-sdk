import asyncio
from asyncio import Event, Lock, Queue, create_task, gather, iscoroutinefunction, to_thread
from collections import defaultdict
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from contree_sdk._internals.models.operation import OperationEvent, OperationEventType
from contree_sdk.utils.typing import AsyncWritable, Writable


if TYPE_CHECKING:
    from contree_sdk.sdk.client._base import _ContreeBase


StreamName = Literal["stderr", "stdout"]


@dataclass
class OutputChunk:
    value: bytes
    stream_name: StreamName


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

    async def _load_events(self):
        async with self._streaming_lock:
            if self._finished_event.is_set():
                return
            async for event in self._client._api.stream_operation_events(self.operation_id, since=self._last_event_id):
                await self._process_event(event)

    async def _process_event(self, event: OperationEvent):
        async with self._processing_lock:
            if event.type in {
                OperationEventType.STDERR,
                OperationEventType.STDOUT,
            }:
                stream_name = str(event.type).lower()
                if "value" not in event.data:
                    raise RuntimeError("Cannot process output event without value")
                value = event.data["value"].encode()
                self._output_by_spid[event.spid][stream_name] += value
                for reader in self._readers_by_spid[event.spid, stream_name]:
                    await reader.write(value)

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
            self._readers_by_spid[spid, stream_name].append(wrapper)

    async def finish(self):
        self._finished_event.set()
        async with self._processing_lock:
            self._readers_by_spid.clear()


EOF = object()


class WriterToQueue:
    def __init__(self, queue: Queue):
        self._queue = queue

    def write(self, data: bytes):
        self._queue.put_nowait(data)

    def close(self):
        self._queue.put_nowait(EOF)


class WriterWrapper:
    def __init__(self, writer: Writable | AsyncWritable):
        self._writer = writer
        write = writer.write
        self._write = write if iscoroutinefunction(write) else partial(to_thread, write)
        close = writer.close
        self._close = close if iscoroutinefunction(close) else partial(to_thread, close)

    async def write(self, data: bytes):
        return await self._write(data)

    async def close(self):
        return await self._close()
