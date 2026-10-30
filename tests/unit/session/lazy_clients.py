"""Controlled transport for tests of the real session and single event reader."""

import asyncio
import queue
import threading
from collections.abc import AsyncGenerator, Iterator
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from contree_client.models import (
    EventDataExit,
    EventDataSpawn,
    EventDataStream,
    EventResources,
    InstanceResult,
    InstanceResultState,
    InstanceSpawnResponse,
    OperationEvent,
    OperationEventType,
    OperationResponse,
    OperationStatus,
    StreamRepr,
)
from contree_client.testing import Call, ContreeAsyncClient, ContreeClient

from tests.unit.session.factories import operation_response, spawn_response


def event(kind: OperationEventType, spid: int = 1, *, exit_code: int = 0) -> OperationEvent:
    data = {}
    if kind == "spawn":
        data = EventDataSpawn(
            pid=spid,
            command="command",
            args=[],
            shell=False,
            cwd="/",
            uid=0,
            gid=0,
            timeout=0,
            truncate_at=1048576,
        )
    elif kind == "exit":
        data = EventDataExit(
            pid=spid,
            code=exit_code,
            signal=-1,
            timed_out=False,
            duration_ms=1,
            resources=EventResources(
                user_time_us=0,
                sys_time_us=0,
                max_rss_kb=0,
                shared_memory=0,
                unshared_memory=0,
                swaps=0,
                minor_faults=0,
                major_faults=0,
                voluntary_ctx_switches=0,
                involuntary_ctx_switches=0,
                block_input_ops=0,
                block_output_ops=0,
                ipc_msgs_sent=0,
                ipc_msgs_received=0,
                signals_received=0,
            ),
        )
    elif kind in {"stdout", "stderr", "stdin"}:
        data = EventDataStream.from_text("")
    return OperationEvent(id=1, ts=datetime.now(timezone.utc), type=kind, spid=spid, data=data)


def subprocess_events(spid: int, result: InstanceResult) -> list[OperationEvent]:
    events = [event("spawn", spid)]
    for name, stream in (("stdout", result.stdout), ("stderr", result.stderr)):
        if isinstance(stream, StreamRepr):
            events.append(replace(event(name, spid), data=EventDataStream.from_bytes(stream.as_bytes())))
    state = result.state
    exit_code = state.exit_code if isinstance(state, InstanceResultState) and isinstance(state.exit_code, int) else 0
    events.append(event("exit", spid, exit_code=exit_code))
    return events


class LiveClient(ContreeClient):
    def __init__(self):
        super().__init__()
        self.mock("resolve_image", "base")
        self.sequence = 0
        self.processes = 1
        self.streams = {}
        self.auto_exit = True
        self.create_error = None
        self.wait_error = None
        self.result_image = True
        self.final_status = OperationStatus.SUCCESS
        self.create_gate = None
        self.wait_gate = None
        self.created = threading.Event()
        self.saving = threading.Event()
        self.results = {}
        self.exit_code = 0

    def result_for_command(self, command: str) -> InstanceResult:
        return InstanceResult(state=InstanceResultState(exit_code=self.exit_code), stdout=StreamRepr.from_text(command))

    def record_call(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self.calls.append(Call(name, args, kwargs))

    def spawn_instance(self, command: str, image: str, **kwargs) -> InstanceSpawnResponse:
        self.record_call("spawn_instance", (command, image), kwargs)
        self.sequence += 1
        operation_id = f"op-{self.sequence}"
        self.streams[operation_id] = queue.Queue()
        return spawn_response(operation_id)

    def operation_subprocess_create(self, operation_id: str, command: str, **kwargs) -> int:
        self.record_call("operation_subprocess_create", (operation_id, command), kwargs)
        self.created.set()
        if self.create_gate is not None and not self.create_gate.wait(3):
            raise TimeoutError("test create gate")
        if self.create_error:
            raise self.create_error
        self.processes += 1
        spid = self.processes
        self.results[operation_id, spid] = self.result_for_command(command)
        events = subprocess_events(spid, self.results[operation_id, spid])
        for item in events if self.auto_exit else events[:-1]:
            self.streams[operation_id].put(item)
        return spid

    def follow_operation_events(self, operation_id: str, **kwargs) -> Iterator[OperationEvent]:
        self.record_call("follow_operation_events", (operation_id,), kwargs)
        while True:
            item = self.streams[operation_id].get(timeout=5)
            if isinstance(item, Exception):
                raise item
            if item is None:
                return
            yield item
            if item.type == "completion":
                return

    def operation_subprocess(self, operation_id: str, spid: int) -> InstanceResult:
        self.record_call("operation_subprocess", (operation_id, spid), {})
        return self.results[operation_id, spid]

    def operation_subprocess_kill(self, operation_id: str, spid: int, **kwargs) -> None:
        self.record_call("operation_subprocess_kill", (operation_id, spid), kwargs)
        self.streams[operation_id].put(event("completion" if spid == 1 else "exit", spid))

    def get_operation_status(self, operation_id: str, **kwargs) -> OperationResponse:
        self.record_call("get_operation_status", (operation_id,), kwargs)
        self.saving.set()
        if self.wait_gate is not None and not self.wait_gate.wait(3):
            raise TimeoutError("test snapshot gate")
        if self.wait_error:
            raise self.wait_error
        return operation_response(
            operation_uuid=operation_id,
            result_image_uuid=f"image-{operation_id}" if self.result_image else None,
            status=self.final_status,
        )

    def cancel_operation(self, operation_id: str) -> None:
        self.record_call("cancel_operation", (operation_id,), {})
        self.streams[operation_id].put(event("completion"))


class LiveAsyncClient(ContreeAsyncClient):
    def __init__(self):
        super().__init__()
        self.mock("resolve_image", "base")
        self.sequence = 0
        self.processes = 1
        self.streams = {}
        self.auto_exit = True
        self.create_error = None
        self.wait_error = None
        self.result_image = True
        self.final_status = OperationStatus.SUCCESS
        self.create_gate = None
        self.wait_gate = None
        self.created = asyncio.Event()
        self.saving = asyncio.Event()
        self.results = {}
        self.exit_code = 0

    def result_for_command(self, command: str) -> InstanceResult:
        return InstanceResult(state=InstanceResultState(exit_code=self.exit_code), stdout=StreamRepr.from_text(command))

    def record_call(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        self.calls.append(Call(name, args, kwargs))

    async def spawn_instance(self, command: str, image: str, **kwargs) -> InstanceSpawnResponse:
        self.record_call("spawn_instance", (command, image), kwargs)
        self.sequence += 1
        operation_id = f"op-{self.sequence}"
        self.streams[operation_id] = asyncio.Queue()
        return spawn_response(operation_id)

    async def operation_subprocess_create(self, operation_id: str, command: str, **kwargs) -> int:
        self.record_call("operation_subprocess_create", (operation_id, command), kwargs)
        self.created.set()
        if self.create_gate is not None:
            await asyncio.wait_for(self.create_gate.wait(), 3)
        if self.create_error:
            raise self.create_error
        self.processes += 1
        spid = self.processes
        self.results[operation_id, spid] = self.result_for_command(command)
        events = subprocess_events(spid, self.results[operation_id, spid])
        for item in events if self.auto_exit else events[:-1]:
            await self.streams[operation_id].put(item)
        return spid

    async def follow_operation_events(self, operation_id: str, **kwargs) -> AsyncGenerator[OperationEvent, None]:
        self.record_call("follow_operation_events", (operation_id,), kwargs)
        while True:
            item = await asyncio.wait_for(self.streams[operation_id].get(), 5)
            if isinstance(item, Exception):
                raise item
            if item is None:
                return
            yield item
            if item.type == "completion":
                return

    async def operation_subprocess(self, operation_id: str, spid: int) -> InstanceResult:
        self.record_call("operation_subprocess", (operation_id, spid), {})
        return self.results[operation_id, spid]

    async def operation_subprocess_kill(self, operation_id: str, spid: int, **kwargs) -> None:
        self.record_call("operation_subprocess_kill", (operation_id, spid), kwargs)
        await self.streams[operation_id].put(event("completion" if spid == 1 else "exit", spid))

    async def get_operation_status(self, operation_id: str, **kwargs) -> OperationResponse:
        self.record_call("get_operation_status", (operation_id,), kwargs)
        self.saving.set()
        if self.wait_gate is not None:
            await asyncio.wait_for(self.wait_gate.wait(), 3)
        if self.wait_error:
            raise self.wait_error
        return operation_response(
            operation_uuid=operation_id,
            result_image_uuid=f"image-{operation_id}" if self.result_image else None,
            status=self.final_status,
        )

    async def cancel_operation(self, operation_id: str) -> None:
        self.record_call("cancel_operation", (operation_id,), {})
        await self.streams[operation_id].put(event("completion"))
