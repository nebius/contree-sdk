from __future__ import annotations

from collections import defaultdict
from contextlib import suppress
from typing import TYPE_CHECKING
from uuid import UUID

from contree_client.models import EventDataExit, EventDataTruncated, OperationStatus, decode_chunk

from contree_sdk.sdk.exceptions import CancelledOperationError, FailedOperationError, OperationTimedOutError
from contree_sdk.sdk.io.writer_wrapper import SyncWriterWrapper
from contree_sdk.sdk.objects.image_like.waiter_common import MAIN_SPID, STREAM_NAMES, OutputChunk, ProcessView
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
        # Caps how much of stdout/stderr we accumulate in `self.outputs`,
        # independent of the server's own `truncate_output_at` -- a safety
        # net against unbounded client-side memory growth if the caller
        # raises or disables that limit. Writers (e.g. a caller-supplied
        # file) still get the full, uncapped chunk.
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
        # Best-effort cleanup, usually called from a `finally` while another
        # exception is already propagating -- suppress broadly so a cancel
        # failure never replaces/masks that original exception.
        with suppress(Exception):
            self.api.cancel_operation(self.operation_id)

    def iter_events(self, timeout: float | None) -> Iterator[tuple[OperationEvent, bytes | None]]:
        # Run at most once per instance (see class docstring): a second
        # caller re-subscribing to an already-drained stream would replay
        # every event through `process_event` again, double-counting
        # output. Once exhausted, accumulated state (`self.outputs` etc.)
        # is already final -- nothing left to yield.
        if self.exhausted:
            return
        completed = False
        try:
            for event in self.api.follow_operation_events(self.operation_id, timeout=timeout):
                chunk = self.process_event(event)
                yield event, chunk
                if event.type == "completion":
                    completed = True
        finally:
            self.exhausted = True
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
            try:
                for _event, _chunk in self.iter_events(timeout):
                    pass
            except TimeoutError as e:
                raise OperationTimedOutError(operation_uuid=UUID(self.operation_id)) from e

        response = self.api.get_operation_status(self.operation_id)
        if response.status == OperationStatus.CANCELLED:
            raise CancelledOperationError(operation_uuid=UUID(self.operation_id))
        if response.status == OperationStatus.FAILED:
            error = value_or_none(response.error) or "Unknown error"
            raise FailedOperationError(operation_uuid=UUID(self.operation_id), error=error)

        exit_event = self.exits.get(spid) if spid is not None else None
        if spid is not None and exit_event is None:
            raise FailedOperationError(
                operation_uuid=UUID(self.operation_id),
                error=f"no exit event received for spid {spid}",
            )
        if exit_event is not None and exit_event.timed_out:
            raise OperationTimedOutError(operation_uuid=UUID(self.operation_id))
        return response, exit_event
