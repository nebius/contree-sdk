from __future__ import annotations

from pathlib import Path
from types import EllipsisType
from typing import Any
from uuid import uuid4

from contree_client.models import ClosableStreamRepr, FileSpec, InstanceResult, OperationResponse, StreamRepr

from contree_sdk.exceptions import FailedOperationError
from contree_sdk.utils.models.file import UploadedFile, UploadFileSpec


RunFiles = list[str | Path | UploadFileSpec] | dict[str, str | Path | bytes | UploadFileSpec] | None


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
        FailedOperationError: The operation itself failed with no result at all
            (a nonzero exit code inside a successful operation is not an error).

    """
    result = or_none(getattr(op.metadata, "result", Ellipsis))
    if result is None:
        raise FailedOperationError(require_str(op.uuid, "operation response missing uuid"), or_none(op.error))
    return result


def exit_code_of(result: InstanceResult) -> int | None:
    state = or_none(result.state)
    return None if state is None else or_none(state.exit_code)


def stream_repr_for_stdin(data: str | bytes) -> ClosableStreamRepr:
    repr_ = StreamRepr.from_text(data) if isinstance(data, str) else StreamRepr.from_bytes(data)
    return ClosableStreamRepr(value=repr_.value, encoding=repr_.encoding, close=True)


def file_spec_for(uploaded: UploadedFile, file: UploadFileSpec) -> FileSpec:
    return FileSpec(uuid=uploaded.uuid, uid=file.uid, gid=file.gid, mode=file.mode)
