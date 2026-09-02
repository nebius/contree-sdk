from __future__ import annotations

import threading
from collections import defaultdict
from contextlib import suppress
from typing import TYPE_CHECKING

from contree_client.models import EventDataExit, EventDataTruncated, OperationStatus, decode_chunk

from contree_sdk.sdk.io.writer_wrapper import SyncWriterWrapper
from contree_sdk.sdk.objects.image_like.waiter_common import (
    MAIN_SPID,
    STREAM_NAMES,
    OutputChunk,
    ProcessView,
    synthetic_exit_event,
)
from contree_sdk.utils.sentinels import value_or_none


if TYPE_CHECKING:
    from collections.abc import Iterator

    from contree_client.base import ContreeSyncClient
    from contree_client.models import OperationEvent, OperationResponse

    from contree_sdk.sdk.io.typing import Writable


class OperationWaiter:
    """Blocking analog of the async waiter.

    A single `for event in follow_operation_events(...)` loop, run at
    most once per instance: sync iteration is inherently one consumer
    at a time, so there's no fan-out/queue machinery to build. Once the
    stream has been drained (by `wait()` or by exhausting `iter_chunks`),
    later callers reuse the accumulated state instead of resubscribing.
    """

    def __init__(self, api: ContreeSyncClient, operation_id: str, *, output_limit: int | None = None) -> None:
        self.api = api
        self.operation_id = operation_id
        self.outputs: dict[int, dict[str, bytearray]] = defaultdict(lambda: defaultdict(bytearray))
        self.writers: dict[tuple[int, str], list[SyncWriterWrapper]] = defaultdict(list)
        self.exits: dict[int, EventDataExit] = {}
        self.truncated: dict[int, dict[str, EventDataTruncated]] = defaultdict(dict)
        self.exhausted = False
        # Reentrant: iter_output()-style composition can call back into wait_for_result()
        # from the same thread while it's still inside iter_events' locked section.
        self.lock = threading.RLock()
        # Caps self.outputs growth only; writers still get the full chunk.
        self.output_limit = output_limit

    def connect_output(self, *, output: Writable, spid: int, stream_name: str) -> None:
        self.writers[spid, stream_name].append(SyncWriterWrapper(output))

    def process_event(self, event: OperationEvent) -> bytes | None:
        spid = event.spid if isinstance(event.spid, int) else 0
        if event.type in {"stdout", "stderr"}:
            chunk = decode_chunk(event.data)
            buffer = self.outputs[spid][event.type]
            if self.output_limit is not None:
                retained = min(len(chunk), max(self.output_limit - len(buffer), 0))
                buffer += chunk[:retained]
            else:
                buffer += chunk
            for writer in self.writers[spid, event.type]:
                writer.write(chunk)
            return chunk
        if isinstance(event.data, EventDataExit):
            self.exits[spid] = event.data
        elif isinstance(event.data, EventDataTruncated):
            self.truncated[spid][event.data.stream] = event.data
        return None

    def finalize_writers(self) -> None:
        for writers in self.writers.values():
            for writer in writers:
                writer.finalize()

    def cancel(self) -> None:
        # Best-effort cleanup: never let this mask an exception already propagating.
        with suppress(Exception):
            self.api.cancel_operation(self.operation_id)

    def iter_events(self, timeout: float | None) -> Iterator[tuple[OperationEvent, bytes | None]]:
        # Locked for the whole body (not just the check) so a second thread calling
        # this concurrently blocks until the first is done, instead of double-subscribing.
        with self.lock:
            if self.exhausted:
                return
            self.exhausted = True
            completed = False
            try:
                for event in self.api.follow_operation_events(self.operation_id, timeout=timeout):
                    chunk = self.process_event(event)
                    yield event, chunk
                    if event.type == "completion":
                        completed = True
            finally:
                if not completed:
                    self.cancel()
                self.finalize_writers()

    def iter_chunks(self, spid: int, timeout: float | None) -> Iterator[OutputChunk]:
        for event, chunk in self.iter_events(timeout):
            # tuple, not a set literal: ty narrows `event.type` through this
            # membership check (needed below) but not through a set literal
            if event.type not in ("stdout", "stderr") or chunk is None:  # noqa: PLR6201
                continue
            event_spid = event.spid if isinstance(event.spid, int) else 0
            if event_spid == spid:
                yield OutputChunk(value=chunk, stream_name=event.type)

    def process_view(self, spid: int = MAIN_SPID) -> ProcessView:
        return ProcessView(
            exit=self.exits.get(spid),
            outputs={name: bytes(self.outputs[spid][name]) for name in STREAM_NAMES},
            truncated=dict(self.truncated[spid]),
        )

    def wait_for_result(
        self, *, timeout: float | None = None, spid: int | None = MAIN_SPID
    ) -> tuple[OperationResponse, EventDataExit | None]:
        if not self.exhausted:
            for _event, _chunk in self.iter_events(timeout):
                pass

        response = self.api.get_operation_status(self.operation_id)
        if response.status == OperationStatus.CANCELLED:
            raise RuntimeError(f"Operation {self.operation_id} was cancelled")
        if response.status == OperationStatus.FAILED:
            error = value_or_none(response.error) or "Unknown error"
            raise RuntimeError(f"Operation {self.operation_id} has failed: {error}")

        exit_event = self.exits.get(spid) if spid is not None else None
        if spid is not None and exit_event is None:
            # self.exits non-empty means another spid's exit is a genuine gap, not a fallback-mode blackout.
            if response.status != OperationStatus.SUCCESS or self.exits:
                raise RuntimeError(f"no exit event received for spid {spid}")
            # Fallback transport mode: only a completion event, no exit -- synthesize one.
            duration_ms = round((value_or_none(response.duration) or 0) * 1000)
            exit_event = synthetic_exit_event(pid=spid, duration_ms=duration_ms)
        if exit_event is not None and exit_event.timed_out:
            raise TimeoutError(f"Operation {self.operation_id} timed out")
        return response, exit_event
