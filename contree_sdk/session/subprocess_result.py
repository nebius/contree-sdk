"""Reconstruct subprocess results from the operation's shared event stream."""

import base64
from dataclasses import fields, replace

from contree_client.models import (
    EventDataExit,
    EventDataSpawn,
    EventDataStream,
    EventDataTruncated,
    EventResources,
    InstanceResult,
    InstanceResultResources,
    InstanceResultState,
    OperationEvent,
    StreamRepr,
)


def integer(value: object) -> int:
    if type(value) is int:
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise ValueError("expected an integer-valued number")


def normalized_exit(data: EventDataExit) -> EventDataExit:
    if not isinstance(data.resources, EventResources):
        raise TypeError("expected resource counters")
    resources = EventResources(**{
        field.name: integer(getattr(data.resources, field.name)) for field in fields(data.resources)
    })
    return replace(
        data,
        pid=integer(data.pid),
        code=integer(data.code),
        signal=integer(data.signal),
        duration_ms=integer(data.duration_ms),
        resources=resources,
    )


def decode_stream(data: EventDataStream) -> bytes:
    if data.encoding == "base64":
        return base64.b64decode(data.value, validate=True)
    if data.encoding == "ascii":
        return data.value.encode("ascii")
    raise ValueError("unsupported stream encoding")


class SubprocessResult:
    """Collect one process's events without requesting its result again."""

    def __init__(self) -> None:
        self.spawn: EventDataSpawn | None = None
        self.exited: EventDataExit | None = None
        self.stdout = bytearray()
        self.stderr = bytearray()
        self.stdout_truncated = False
        self.stderr_truncated = False
        self.error: RuntimeError | None = None

    def observe(self, event: OperationEvent) -> None:
        """Consume an event and reject malformed lifecycle or output data."""
        if self.error is not None:
            raise self.error
        try:
            self.consume(event)
        except (ValueError, TypeError) as error:
            self.error = RuntimeError(f"invalid subprocess {event.type} event: {error}")
            raise self.error from error

    def consume(self, event: OperationEvent) -> None:
        data = event.data
        if event.type == "spawn":
            if not isinstance(data, EventDataSpawn) or self.spawn is not None:
                raise ValueError("expected one spawn payload")
            self.spawn = replace(data, pid=integer(data.pid), truncate_at=integer(data.truncate_at))
        elif event.type == "exit":
            if not isinstance(data, EventDataExit) or self.exited is not None:
                raise ValueError("expected one exit payload")
            self.exited = normalized_exit(data)
        elif event.type in {"stdout", "stderr"}:
            if not isinstance(data, EventDataStream):
                raise TypeError("expected a stream payload")
            if self.spawn is None:
                raise ValueError("output arrived without a spawn event")
            self.append_output(event.type, decode_stream(data), truncated=data.truncated is True)
        elif event.type == "truncated":
            if not isinstance(data, EventDataTruncated):
                raise TypeError("expected a truncation payload")
            if data.stream == "stdout":
                self.stdout_truncated = True
            elif data.stream == "stderr":
                self.stderr_truncated = True
        elif event.type == "size_cap":
            self.stdout_truncated = True
            self.stderr_truncated = True

    def append_output(self, stream: str, chunk: bytes, *, truncated: bool) -> None:
        if self.spawn is None:
            raise ValueError("output arrived without a spawn event")
        output = self.stdout if stream == "stdout" else self.stderr
        limit = self.spawn.truncate_at
        remaining = max(0, limit - len(output)) if limit > 0 else len(chunk)
        output.extend(chunk[:remaining])
        if truncated or len(chunk) > remaining:
            if stream == "stdout":
                self.stdout_truncated = True
            else:
                self.stderr_truncated = True

    def result(self) -> InstanceResult:
        if self.error is not None:
            raise self.error
        if self.spawn is None or self.exited is None:
            raise RuntimeError("subprocess event stream is incomplete: spawn and exit are required")
        exited = self.exited
        usage = exited.resources
        user_time = usage.user_time_us / 1e6
        system_time = usage.sys_time_us / 1e6
        stdout = StreamRepr.from_bytes(bytes(self.stdout))
        stderr = StreamRepr.from_bytes(bytes(self.stderr))
        stdout.truncated = self.stdout_truncated
        stderr.truncated = self.stderr_truncated
        return InstanceResult(
            state=InstanceResultState(
                pid=self.spawn.pid,
                exit_code=exited.code,
                signal=exited.signal,
                timed_out=exited.timed_out,
                core_dump=exited.core_dump is True,
                oom_killed=exited.oom_killed is True,
                continued=False,
                stopped=False,
            ),
            resources=InstanceResultResources(
                block_input=usage.block_input_ops,
                block_output=usage.block_output_ops,
                elapsed_time=user_time + system_time,
                involuntary_switches=usage.involuntary_ctx_switches,
                max_rss=usage.max_rss_kb,
                monotonic_time=exited.duration_ms / 1e3,
                page_faults=usage.major_faults,
                page_faults_io=usage.minor_faults,
                shared_memory=usage.shared_memory,
                signals=usage.signals_received,
                swaps=usage.swaps,
                system_cpu_time=system_time,
                unshared_memory=usage.unshared_memory,
                user_cpu_time=user_time,
                voluntary_switches=usage.voluntary_ctx_switches,
            ),
            stdout=stdout,
            stderr=stderr,
        )
