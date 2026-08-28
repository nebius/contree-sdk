from __future__ import annotations

from copy import copy
from dataclasses import replace
from datetime import timedelta
from math import ceil
from typing import TYPE_CHECKING, Any, TypeVar, overload
from uuid import UUID

from contree_sdk.sdk.exceptions import ContreeImageStateError, DisposableImageRunError
from contree_sdk.sdk.io.typing import INPUT_TYPES, OUTPUT_REQUEST_TYPES, OUTPUT_TYPES
from contree_sdk.sdk.objects.image_like.state import (
    STATE_MACHINE,
    ImageState,
    Prepared,
    Pulled,
    StateData,
    StateDataT,
    Succeeded,
    WithRequest,
)
from contree_sdk.sdk.objects.run import RunRequest
from contree_sdk.utils.models.file import UploadFileSpec


if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from contree_sdk.sdk.objects.image_like.result import ContreeResult

FileTypeT = TypeVar("FileTypeT")
DirTypeT = TypeVar("DirTypeT")

ImageLikeT = TypeVar("ImageLikeT", bound="ImageLikeBase")


class ImageLikeBase:
    """State/data shared by the sync and async image-like objects.

    Holds no client and does no I/O: building a `RunRequest`, walking
    the state machine, and reading back the result are pure. Real I/O
    (`start()`, `wait()`, `ls()`, ...) lives in `_async.py`/`_sync.py`,
    each calling its own `contree_client` backend directly.
    """

    uuid: UUID | None
    """Unique identifier of the image."""
    tag: str | None
    """Optional tag associated with the image."""

    def __init__(self, client: Any, uuid: UUID | str | None, tag: str | None):
        """Initialize image-like object.

        Args:
        client: The ConTree client instance (`ContreeSync`/`Contree`).
        uuid: Image UUID as string or UUID object.
        tag: Optional tag for the image.

        """
        self.uuid = UUID(uuid) if isinstance(uuid, str) else uuid
        self.tag = tag
        self.client = client
        self.state_data: StateData = Pulled()

    # utils methods

    def copy_self(self: ImageLikeT) -> ImageLikeT:
        return copy(self)

    def copy_with_state(self: ImageLikeT, data: StateData) -> ImageLikeT:
        new_self = self.copy_self()
        new_self.set_state(data)
        return new_self

    # main methods

    @overload
    def run(
        self: ImageLikeT,
        command: str,
        *,
        args: Iterable[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        hostname: str | None = None,
        stdin: INPUT_TYPES | None = None,
        stdout: OUTPUT_REQUEST_TYPES | None = str,
        stderr: OUTPUT_REQUEST_TYPES | None = str,
        tag: str | None = None,
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | bytes | UploadFileSpec] | None = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
        preserve_env: bool = False,
    ) -> ImageLikeT: ...

    @overload
    def run(
        self: ImageLikeT,
        *,
        shell: str,
        args: Iterable[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        hostname: str | None = None,
        stdin: INPUT_TYPES | None = None,
        stdout: OUTPUT_REQUEST_TYPES | None = str,
        stderr: OUTPUT_REQUEST_TYPES | None = str,
        tag: str | None = None,
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | bytes | UploadFileSpec] | None = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
        preserve_env: bool = False,
    ) -> ImageLikeT: ...

    def run(  # noqa: PLR0913
        self: ImageLikeT,
        command: str | None = None,
        *,
        shell: str | None = None,
        args: Iterable[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        hostname: str | None = None,
        stdin: INPUT_TYPES | None = None,
        stdout: OUTPUT_REQUEST_TYPES | None = str,
        stderr: OUTPUT_REQUEST_TYPES | None = str,
        tag: str | None = None,
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | bytes | UploadFileSpec] | None = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
        preserve_env: bool = False,
    ) -> ImageLikeT:
        """Prepare image for command execution.

        Args:
            command: Command to execute (mutually exclusive with shell).
            shell: Shell command string (mutually exclusive with command).
            args: Command arguments.
            env: Environment variables.
            cwd: Working directory inside the image.
            hostname: Hostname for the container.
            stdin: Input source.
            stdout: Output destination for stdout.
            stderr: Output destination for stderr.
            tag: Tag for the resulting image.
            files: Files to upload into the image.
            timeout: Execution timeout in seconds or as timedelta.
            disposable: If True, image is discarded after execution.
            truncate_output_at: number of bytes to truncate stdout and stderr. Defaults to default_truncate_output_at
            preserve_env: If True, environment variables are preserved in resulting image after execution.

        Returns:
            New image instance configured for execution.

        Raises:
            DisposableImageRunError: If attempting to run on a disposed image.
            ValueError: If neither command nor shell is provided.

        """
        if not self.uuid and not self.tag:
            raise DisposableImageRunError
        if shell is not None:
            command = shell
        if command is None:
            raise ValueError("Either command or shell must be provided")

        if timeout is not None:
            if isinstance(timeout, timedelta):
                timeout = timeout.total_seconds()
            timeout = ceil(timeout)
        request = RunRequest(
            command=command,
            args=list(args or []),
            shell=shell is not None,
            env=dict(env or {}),
            cwd=cwd,
            timeout=timeout,
            tag=tag or None,
            hostname=hostname or "hostname",
            stdin=stdin,
            files=UploadFileSpec.prepare_files(files or []),
            stdout=stdout,
            stderr=stderr,
            disposable=disposable,
            truncate_output_at=truncate_output_at,
            preserve_env=preserve_env,
        )
        return self.copy_with_state(Prepared(request=request))

    def update_request(self: ImageLikeT, **kwargs) -> ImageLikeT:
        prepared = self.ensure_state(Prepared)
        return self.copy_with_state(Prepared(request=replace(prepared.request, **kwargs)))

    # internal methods

    def ensure_state(self, state_type: type[StateDataT]) -> StateDataT:
        data = self.state_data
        if not isinstance(data, state_type):
            raise ContreeImageStateError(image_uuid=self.uuid, state=self.state, states=[state_type.state])
        return data

    def set_state(self, data: StateData) -> None:
        possible_states = STATE_MACHINE.get(self.state, frozenset())
        if data.state not in possible_states:
            raise ContreeImageStateError(image_uuid=self.uuid, state=self.state, states=list(possible_states))
        self.state_data = data

    @property
    def state(self) -> ImageState:
        """Current state of the image in the execution lifecycle."""
        return self.state_data.state

    def __repr__(self):
        other = ""
        if self.tag:
            other += f", tag={self.tag}"
        try:
            result = self.result
            result_str = f", result={result}"
        except ContreeImageStateError:
            result_str = ""
        return f"{type(self).__name__}(uuid={self.uuid!r}, state={self.state!r}{other}{result_str})"

    # result methods

    @property
    def result(self) -> ContreeResult:
        """Execution result. Only available after successful execution."""
        return self.ensure_state(Succeeded).result

    @property
    def request(self) -> RunRequest | None:
        data = self.state_data
        return data.request if isinstance(data, WithRequest) else None

    @property
    def stdin(self) -> INPUT_TYPES | None:
        """Configured stdin source."""
        return self.request.stdin if self.request else None

    @property
    def stdout(self) -> OUTPUT_TYPES | None:
        """Stdout output from the execution."""
        return self.result.stdout

    @property
    def stderr(self) -> OUTPUT_TYPES | None:
        """Stderr output from the execution."""
        return self.result.stderr

    @property
    def exit_code(self) -> int:
        """Exit code of the executed command."""
        return self.result.exit_code

    @property
    def elapsed(self) -> timedelta:
        """Time elapsed during execution."""
        return self.result.elapsed_time
