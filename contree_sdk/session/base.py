from __future__ import annotations

from io import TextIOBase
from types import EllipsisType
from typing import IO, Any, Literal, cast
from uuid import uuid4

from contree_client.models import (
    ClosableStreamRepr,
    EventDataStream,
    FileSpec,
    InstanceResult,
    OperationResponse,
    OperationStatus,
    StreamRepr,
)

from contree_sdk.exceptions import FailedOperationError
from contree_sdk.files import RunFiles  # noqa: F401 - public re-export for existing module users
from contree_sdk.utils.models.file import UploadedFile, UploadFileSpec


def or_none(value: Any) -> Any | None:
    return None if value is Ellipsis else value


def require_str(value: str | EllipsisType | None, message: str) -> str:
    if value is None or isinstance(value, EllipsisType):
        raise ValueError(message)
    return value


def new_session_id() -> str:
    return uuid4().hex


def validate_command(command: str | None, shell: str | None) -> str:
    if command is not None and shell is not None:
        raise ValueError("command and shell are mutually exclusive")
    resolved = shell if shell is not None else command
    if resolved is None:
        raise ValueError("either command or shell must be provided")
    return resolved


def instance_result(op: OperationResponse) -> InstanceResult:
    """Get the operation's `InstanceResult`.

    Returns:
        The `InstanceResult` from `op.metadata.result`.

    Raises:
        InterruptedError: The operation was cancelled.
        FailedOperationError: The operation itself failed with no result at all
            (a nonzero exit code inside a successful operation is not an error).

    """
    if op.status == OperationStatus.CANCELLED:
        raise InterruptedError(f"operation {op.uuid} was cancelled")
    if op.status != OperationStatus.SUCCESS:
        raise FailedOperationError(require_str(op.uuid, "operation response missing uuid"), or_none(op.error))
    result = or_none(getattr(op.metadata, "result", Ellipsis))
    if result is None:
        raise FailedOperationError(require_str(op.uuid, "operation response missing uuid"), or_none(op.error))
    return result


def exit_code_of(result: InstanceResult) -> int | None:
    state = or_none(result.state)
    return None if state is None else or_none(state.exit_code)


def stream_repr_for_stdin(data: str | bytes, *, close: bool = True) -> ClosableStreamRepr:
    repr_ = StreamRepr.from_text(data) if isinstance(data, str) else StreamRepr.from_bytes(data)
    return ClosableStreamRepr(value=repr_.value, encoding=repr_.encoding, close=close)


def file_spec_for(uploaded: UploadedFile, file: UploadFileSpec) -> FileSpec:
    return FileSpec(uuid=uploaded.uuid, uid=file.uid, gid=file.gid, mode=file.mode)


def encode_stdin_chunk(data: str | bytes) -> tuple[str, Literal["ascii", "base64"]]:
    payload = StreamRepr.from_text(data) if isinstance(data, str) else StreamRepr.from_bytes(data)
    return payload.value, payload.encoding


def write_stream_chunk(stream: IO[str] | IO[bytes], data: object) -> None:
    if not isinstance(data, EventDataStream):
        raise TypeError("expected an EventDataStream payload")
    if isinstance(stream, TextIOBase):
        cast("IO[str]", stream).write(data.as_text())
    else:
        cast("IO[bytes]", stream).write(data.as_bytes())
