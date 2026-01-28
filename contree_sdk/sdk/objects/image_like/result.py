from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from contree_sdk._internals.models.instance import InstanceOperationMetadata
from contree_sdk.sdk.objects.run import REQUEST_IO_TYPES, RunRequest
from contree_sdk.utils.codecs import io_decode
from contree_sdk.utils.io_wrap import IO_TYPES, IOMode, PipeIO, get_io_by_obj
from contree_sdk.utils.models.stream import StreamDescription


@dataclass(frozen=True)
class ContreeResult:
    stderr: IO_TYPES | None
    stdout: IO_TYPES | None
    exit_code: int
    elapsed_time: timedelta
    cost: float

    _raw: InstanceOperationMetadata | None = None

    @classmethod
    def from_result(cls, raw_result: InstanceOperationMetadata, request: RunRequest) -> ContreeResult:
        if raw_result.result is None:
            raise RuntimeError("Result cannot be found")
        return cls(
            exit_code=raw_result.result.state.exit_code,
            stdout=cls._parse_io(raw_result.result.stdout, request.stdout),
            stderr=cls._parse_io(raw_result.result.stderr, request.stderr),
            elapsed_time=timedelta(seconds=raw_result.result.resources.elapsed_time),
            cost=raw_result.result.resources.cost,
            _raw=raw_result,
        )

    @classmethod
    def _parse_io(cls, raw_io: StreamDescription, expected: REQUEST_IO_TYPES) -> IO_TYPES | None:
        parsed = io_decode(raw_io)
        if expected is bytes:
            return parsed
        if expected is str or expected is None:
            return parsed.decode()
        io_obj = get_io_by_obj(expected, IOMode.write)
        if io_obj is None:
            return None

        try:
            io_obj.write(parsed)
        except TypeError:  # IO[str]
            io_obj.write(parsed.decode())

        io_obj.flush()
        if isinstance(io_obj, PipeIO):
            io_obj.close()

        return io_obj
