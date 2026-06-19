from __future__ import annotations

from asyncio import gather, to_thread
from collections.abc import Iterable
from copy import copy
from dataclasses import replace
from datetime import timedelta
from io import IOBase
from math import ceil
from pathlib import Path, PurePosixPath
from typing import IO, TYPE_CHECKING, TypeVar, overload
from uuid import UUID

import cattrs

from contree_sdk._internals.models.instance import InstanceFileSpec, InstanceOperationMetadata, InstanceSpawnRequest
from contree_sdk.sdk.exceptions import ContreeImageStateError, DisposableImageRunError
from contree_sdk.sdk.objects.image_like.result import ContreeResult
from contree_sdk.sdk.objects.image_like.state import ImageState
from contree_sdk.sdk.objects.run import REQUEST_IO_TYPES, RunRequest
from contree_sdk.utils.codecs import io_encode
from contree_sdk.utils.io_wrap import IO_TYPES, IOMode, get_io_by_obj
from contree_sdk.utils.models.file import UploadedFile, UploadFileSpec
from contree_sdk.utils.models.stream import StreamDescription


if TYPE_CHECKING:
    from contree_sdk.sdk.client._base import _ContreeBase

_PREPARATION_STATES = frozenset({ImageState.PREPARING, ImageState.PREPARED})

"""
Permitted state transitions.

Mapping:
    from_state -> allowed to_states
"""
_STATE_MACHINE: dict[ImageState, frozenset[ImageState]] = {
    ImageState.PULLED: _PREPARATION_STATES,
    ImageState.PREPARING: _PREPARATION_STATES,
    ImageState.PREPARED: frozenset({ImageState.EXECUTING}),
    ImageState.EXECUTING: frozenset({ImageState.SUCCEEDED}),
    ImageState.SUCCEEDED: _PREPARATION_STATES,
}

FileTypeT = TypeVar("FileTypeT")
DirTypeT = TypeVar("DirTypeT")

_T = TypeVar("_T", bound="_ImageLikeBase")


class _ImageLikeBase:
    """Base class for image-like objects that can execute commands."""

    uuid: UUID | None
    """Unique identifier of the image."""
    tag: str | None
    """Optional tag associated with the image."""

    def __init__(self, client: _ContreeBase, uuid: UUID | str | None, tag: str | None):
        """Initialize image-like object.

        Args:
        client: The ConTree client instance.
        uuid: Image UUID as string or UUID object.
        tag: Optional tag for the image.

        """
        self.uuid = UUID(uuid) if isinstance(uuid, str) else uuid
        self.tag = tag
        self._client = client
        self._request: RunRequest | None = None
        self._stdin = None
        self._result: ContreeResult | None = None
        self._state = ImageState.PULLED

    # utils methods
    def _copy_self(self: _T, clear: bool = True) -> _T:
        new_self = copy(self)
        if clear:
            new_self._result = None
        return new_self

    # main methods

    @overload
    def run(
        self: _T,
        command: str,
        *,
        args: Iterable[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        hostname: str | None = None,
        stdin: IO_TYPES | None = None,
        stdout: REQUEST_IO_TYPES | None = None,
        stderr: REQUEST_IO_TYPES | None = None,
        tag: str | None = None,
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | UploadFileSpec] | None = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
    ) -> _T: ...

    @overload
    def run(
        self: _T,
        *,
        shell: str,
        args: Iterable[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        hostname: str | None = None,
        stdin: IO_TYPES | None = None,
        stdout: REQUEST_IO_TYPES | None = None,
        stderr: REQUEST_IO_TYPES | None = None,
        tag: str | None = None,
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | UploadFileSpec] | None = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
    ) -> _T: ...

    def run(  # noqa: PLR0913
        self: _T,
        command: str | None = None,
        *,
        shell: str | None = None,
        args: Iterable[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        hostname: str | None = None,
        stdin: IO_TYPES | None = None,
        stdout: REQUEST_IO_TYPES | None = None,
        stderr: REQUEST_IO_TYPES | None = None,
        tag: str | None = None,
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | UploadFileSpec] | None = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
    ) -> _T:
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

        Returns:
            New image instance configured for execution.

        Raises:
            DisposableImageRunError: If attempting to run on a disposed image.
            ValueError: If neither command nor shell is provided.

        """
        if not self.uuid and not self.tag:
            raise DisposableImageRunError
        new_self = self._copy_self()
        new_self._transition_state(ImageState.PREPARED)
        if shell is not None:
            command = shell
        if command is None:
            raise ValueError("Either command or shell must be provided")

        if timeout is not None:
            if isinstance(timeout, timedelta):
                timeout = timeout.total_seconds()
            timeout = ceil(timeout)
        new_self._request = RunRequest(
            command=command,
            args=list(args or []),
            shell=shell is not None,
            env=dict(env or {}),
            cwd=cwd,
            timeout=timeout,
            tag=tag or None,
            hostname=hostname or "hostname",
            stdin=stdin,
            files=UploadFileSpec._prepare_files(files or []),
            stdout=stdout,
            stderr=stderr,
            disposable=disposable,
            truncate_output_at=truncate_output_at,
        )
        new_self._prepare_stdin(stdin)
        return new_self

    async def _apply_files(
        self: _T,
        *args: str | Path | UploadFileSpec | list[str | Path | UploadFileSpec] | dict[str, str | Path | UploadFileSpec],
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | UploadFileSpec] | None = None,
    ) -> _T:
        """Upload files into a new image derived from this one.

        Args:
            *args: Files to upload.
            files: Files as a list or a dict mapping destination paths to sources.
                When both args and files are provided, they are merged.

        Returns:
            New image with the uploaded files baked in.

        """
        prepared_files = []
        for arg in args:
            if isinstance(arg, (list, dict)):
                prepared_files.extend(UploadFileSpec._prepare_files(arg))
            else:
                prepared_files.append(arg)

        return await self.run(
            shell="true",
            files=(prepared_files + (UploadFileSpec._prepare_files(files) if files else [])),
            disposable=False,
        )._await()

    async def _prepare_files_for_api(self, files: list[UploadFileSpec]) -> dict[str, InstanceFileSpec]:
        async def _upload_file(file: UploadFileSpec) -> tuple[str, InstanceFileSpec]:
            source = file.source
            if not isinstance(source, UploadedFile):
                source = await self._client.files._upload_file(source)
            return str(file.path), InstanceFileSpec(
                uuid=source.uuid,
                mode=f"{file.mode:04o}",
                uid=file.uid,
                gid=file.gid,
            )

        return dict(await gather(*(_upload_file(i) for i in files)))

    def _prepare_stdin(self, stdin: IO_TYPES | None):
        stdin = stdin or ""
        io_obj = get_io_by_obj(stdin, IOMode.read)
        self._stdin = io_obj  # todo do it on run or stdin_from

    def _update_request(self: _T, **kwargs) -> _T:
        self._assert_states(ImageState.PREPARED)
        new_self = self._copy_self()
        if self._request is None:
            raise RuntimeError("Request is not prepared")
        self._request = replace(self._request, **kwargs)
        if stdin := kwargs.get("stdin"):
            new_self._prepare_stdin(stdin)
        return new_self

    def _read_stdin(self) -> StreamDescription:
        if self._stdin is None:
            return io_encode("")
        return io_encode(self._stdin.read())

    # internal methods

    def _assert_states(self, *states: ImageState) -> None:
        if self.state not in set(states):
            raise ContreeImageStateError(image_uuid=self.uuid, state=self.state, states=list(states))

    def _can_transition(self, state: ImageState):
        possible_states = _STATE_MACHINE.get(self._state, set())
        if state not in possible_states:
            raise ContreeImageStateError(image_uuid=self.uuid, state=self.state, states=list(possible_states))

    def _transition_state(self, state: ImageState):
        self._can_transition(state)
        self._state = state

    @property
    def state(self) -> ImageState:
        """Current state of the image in the execution lifecycle."""
        return self._state

    async def _await(self: _T) -> _T:
        req = self._request
        if req is None:
            raise RuntimeError("Run request has not been set")
        new_self = self._copy_self()  # todo add support for start() method
        new_self._transition_state(ImageState.EXECUTING)

        files, stdin = await gather(new_self._prepare_files_for_api(req.files), to_thread(new_self._read_stdin))

        timeout = req.timeout
        if timeout is None:
            timeout = self._client.config.operation_run_timeout or self._client.config.operation_timeout

        self._client._warn_if_timeout_exceeds_limit(timeout, "instance_max_timeout")

        operation_uuid = await self._client._start_operation(
            InstanceSpawnRequest(
                command=req.command,
                image=f"tag:{self.tag}" if self.uuid is None else str(self.uuid),
                hostname=req.hostname or "localhost",
                args=req.args or [],
                env=req.env,
                shell=bool(req.shell),
                cwd=req.cwd or "",
                disposable=req.disposable,
                timeout=round(timeout or self._client.config.operation_timeout),
                stdin=stdin,
                files=files,
                truncate_output_at=req.truncate_output_at or self._client.config.default_truncate_output_at,
            )
        )
        image_metadata, result = await self._client._wait_operation(
            operation_uuid, InstanceOperationMetadata, timeout=timeout
        )

        new_self._transition_state(ImageState.SUCCEEDED)
        new_uuid = result.image
        new_self.uuid = new_uuid and UUID(new_uuid)
        new_self.tag = result.tag
        new_self._result = ContreeResult.from_result(image_metadata, request=req)
        if req.tag:
            new_self = await new_self._tag_as(req.tag)
        return new_self

    # inspect methods

    async def _ls(
        self, path: str | PurePosixPath, file_type: type[FileTypeT], dir_type: type[DirTypeT]
    ) -> list[FileTypeT | DirTypeT]:
        uuid = self.uuid if self.uuid is not None else (await self._client._api.get_image_by_tag(self.tag or "")).uuid
        ls_res = await self._client._api.list_image_files(uuid, path)
        result = []
        for obj in ls_res:
            type_ = dir_type if obj.is_dir else file_type
            result.append(
                type_(
                    _image=self,
                    _path=PurePosixPath(path),
                    **cattrs.unstructure(obj),
                )
            )
        return result

    async def _read_file(self, path: str | PurePosixPath) -> bytes:
        uuid = self.uuid if self.uuid is not None else (await self._client._api.get_image_by_tag(self.tag or "")).uuid
        return await self._client._api.download_image_file(uuid, path)

    async def _download(self, image_path: str | PurePosixPath, local_path: str | Path | None = None) -> Path:
        image_path = PurePosixPath(image_path)
        if local_path is None:
            local_path = image_path.name
        with await to_thread(open, local_path, "wb") as file:
            await to_thread(file.write, await self._read_file(image_path))
        return Path(local_path)

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
        """Execution result. Only available after successful execution.

        Raises:
            RuntimeError: If the result hasn't been set.

        """
        self._assert_states(ImageState.SUCCEEDED)
        if self._result is None:
            raise RuntimeError("Result has not been set")
        return self._result

    @property
    def stdin(self) -> IO | IOBase | None:
        """Configured stdin source."""
        return self._stdin

    @property
    def stdout(self) -> IO_TYPES:
        """Stdout output from the execution."""
        return self.result.stdout

    @property
    def stderr(self) -> IO_TYPES:
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

    async def _tag_as(self: _T, tag: str | None) -> _T:
        """Tag this image with the specified tag, or remove the tag if None.

        Args:
            tag: Tag name to apply to the image, or None to remove the tag.

        Returns:
            New instance with updated tag.

        """
        if tag is None:
            return await self._untag()
        await self._client._api.tag_image(str(self.uuid), tag)
        new_self = self._copy_self(clear=False)
        new_self.tag = tag
        return new_self

    async def _untag(self: _T) -> _T:
        """Remove the tag from this image.

        Returns:
            New instance with tag set to None.

        """
        await self._client._api.untag_image(str(self.uuid))
        new_self = self._copy_self(clear=False)
        new_self.tag = None
        return new_self
