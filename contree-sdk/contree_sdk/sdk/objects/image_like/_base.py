from __future__ import annotations

from asyncio import gather, to_thread
from collections.abc import Iterable
from copy import copy
from dataclasses import replace
from datetime import timedelta
from math import ceil
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any, Self, TypeVar
from uuid import UUID

import cattrs

from contree_sdk._internals.models.instance import InstanceFileSpec, InstanceOperationMetadata, InstanceSpawnRequest
from contree_sdk._internals.utils.exception import wrap_api_call
from contree_sdk.sdk.exceptions import ContreeImageStateError, DisposableImageRunError
from contree_sdk.sdk.objects.image_like.result import ContreeResult
from contree_sdk.sdk.objects.image_like.state import ImageState
from contree_sdk.sdk.objects.run import RunRequest
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


class _ImageLikeBase:
    """Base class for image-like objects that can execute commands."""

    uuid: UUID
    """Unique identifier of the image."""
    tag: str | None
    """Optional tag associated with the image."""

    def __init__(self, client: _ContreeBase, uuid: UUID | str, tag: str | None):
        """Initialize image-like object.

        Args:
        client: The Contree client instance.
        uuid: Image UUID as string or UUID object.
        tag: Optional tag for the image.

        """
        self.uuid: UUID | None = UUID(uuid) if isinstance(uuid, str) else uuid
        self.tag: str | None = tag
        self._client = client
        self._request: RunRequest | None = None
        self._stdin = None
        self._result: ContreeResult | None = None
        self._state = ImageState.PULLED

    # command methods
    def command(self, command: str, /) -> Self:
        raise NotImplementedError

    def shell(self, command: str, /) -> Self:
        raise NotImplementedError

    # run arguments methods
    def args(self, *args: str) -> Self:
        raise NotImplementedError

    def stdin_from(self, stdin: IO_TYPES, /) -> Self:
        raise NotImplementedError

    def cwd(self, cwd: str, /) -> Self:
        raise NotImplementedError

    def env(self, env: dict = None, **envs) -> Self:
        raise NotImplementedError

    def stdout_to(self, stdout: IO_TYPES, /) -> Self:
        raise NotImplementedError

    def stderr_to(self, stderr: IO_TYPES, /) -> Self:
        raise NotImplementedError

    def add_tag(self, tag: str, /) -> Self:
        raise NotImplementedError

    def add_file(self, file_desc: Any) -> Self:
        raise NotImplementedError

    # utils methods

    def _copy_self(self, clear: bool = True) -> Self:
        new_self = copy(self)
        if clear:
            new_self._stdout = new_self._stderr = new_self._raw_result = None
        return new_self

    # main methods

    def run(  # noqa: PLR0913
        self,
        command: str = None,
        shell: str = None,
        args: Iterable[str] | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        hostname: str | None = None,
        stdin: IO_TYPES | None = None,
        stdout: IO_TYPES | None = None,
        stderr: IO_TYPES | None = None,
        tag: str | None = None,
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | UploadFileSpec] | None = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
    ) -> Self:
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

        Returns:
            New image instance configured for execution.

        Raises:
            DisposableImageRunError: If attempting to run on a disposed image.

        """
        if not self.uuid:
            raise DisposableImageRunError
        new_self = self._copy_self()
        new_self._transition_state(ImageState.PREPARED)
        if shell is not None:
            command = shell

        if timeout is not None:
            if isinstance(timeout, timedelta):
                timeout = timeout.total_seconds()
            timeout = ceil(timeout)
        new_self._request = RunRequest(
            command=command,
            args=list(args or []),
            shell=shell is not None,
            env=dict(env or {}),
            cwd=cwd or "/",
            timeout=timeout,
            tag=tag or None,  # todo use tag later
            hostname=hostname or "hostname",
            stdin=stdin,
            files=self._prepare_files(files or []),
            stdout=stdout,
            stderr=stderr,
            disposable=disposable,
        )
        new_self._prepare_stdin(stdin)
        return new_self

    def _prepare_files(
        self,
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | UploadFileSpec],
        default_image_path: str = "/",
    ) -> list[UploadFileSpec]:
        prepared = []
        if isinstance(files, dict):
            for image_path, file in files.items():
                if isinstance(file, UploadFileSpec):
                    item = replace(file, path=Path(image_path))
                else:
                    item = UploadFileSpec(
                        path=Path(image_path),
                        source=file,
                    )
                prepared.append(item)
            return prepared
        for file in files:
            if isinstance(file, UploadFileSpec):
                prepared.append(file)
            else:
                local_path = Path(file)
                image_path = Path(default_image_path) / local_path.name
                prepared.append(
                    UploadFileSpec(
                        path=Path(image_path),
                        source=local_path,
                    )
                )
        return prepared

    async def _prepare_files_for_api(self, files: list[UploadFileSpec]) -> dict[str, InstanceFileSpec]:
        async def _upload_file(file: UploadFileSpec) -> tuple[str, InstanceFileSpec]:
            if not isinstance(file.source, UploadedFile):
                file = replace(file, source=await self._client.files._upload_file(file.source))
            return str(file.path), InstanceFileSpec(
                uuid=file.source.uuid,
                mode=f"{file.mode:04o}",
                uid=file.uid,
                gid=file.gid,
            )

        return dict(await gather(*(_upload_file(i) for i in files)))

    def _prepare_stdin(self, stdin: IO_TYPES | None):
        stdin = stdin or ""
        io_obj = get_io_by_obj(stdin, IOMode.read)
        self._stdin = io_obj  # todo do it on run or stdin_from

    def _update_request(self, **kwargs) -> Self:
        self._assert_states(ImageState.PREPARED)
        new_self = self._copy_self()
        self._request = replace(self._request, **kwargs)
        if stdin := kwargs.get("stdin"):
            new_self._prepare_stdin(stdin)
        return new_self

    def _read_stdin(self) -> StreamDescription:
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

    async def _await(self) -> Self:
        req = self._request
        new_self = self._copy_self()  # todo add support for start() method
        new_self._transition_state(ImageState.EXECUTING)

        files, stdin = await gather(new_self._prepare_files_for_api(req.files), to_thread(new_self._read_stdin))

        timeout = req.timeout
        if timeout is None:
            timeout = self._client.config.operation_run_timeout or self._client.config.operation_timeout

        with wrap_api_call():
            operation_uuid = await self._client._api.spawn_instance(
                InstanceSpawnRequest(
                    command=req.command,
                    image=str(self.uuid),
                    hostname=req.hostname,
                    args=req.args,
                    env=req.env,
                    shell=req.shell,
                    cwd=req.cwd,
                    disposable=req.disposable,
                    timeout=timeout,
                    stdin=stdin,
                    files=files,
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
        return new_self

    # inspect methods

    async def _ls(
        self, path: str | Path, file_type: type[FileTypeT], dir_type: type[DirTypeT]
    ) -> list[FileTypeT | DirTypeT]:
        with wrap_api_call():
            ls_res = await self._client._api.list_image_files(self.uuid, path)
        result = []
        for obj in ls_res:
            type_ = dir_type if obj.is_dir else file_type
            result.append(
                type_(
                    _image=self,
                    _path=Path(path),
                    **cattrs.unstructure(obj),
                )
            )
        return result

    async def _read_file(self, path: Path) -> bytes:
        with wrap_api_call():
            return await self._client._api.download_image_file(self.uuid, path)

    async def _download(self, image_path: str | Path, local_path: str | Path | None = None) -> Path:
        image_path = Path(image_path)
        if local_path is None:
            local_path = image_path.name
        with await to_thread(open, local_path, "wb") as file:
            await to_thread(file.write, await self._read_file(image_path))
        return local_path

    def __repr__(self):
        other = ""
        if self.tag:
            other += f", tag={self.tag}"
        return f"{type(self).__name__}(uuid={self.uuid!r}, state={self.state!r}{other})"

    # result methods

    @property
    def result(self) -> ContreeResult:
        """Execution result. Only available after successful execution."""
        self._assert_states(ImageState.SUCCEEDED)
        return self._result

    @property
    def stdin(self) -> IO | None:
        """Configured stdin source."""
        return self._stdin

    @property
    def stdout(self) -> IO_TYPES | None:
        """Stdout output from the execution."""
        return self.result.stdout

    @property
    def stderr(self) -> IO_TYPES | None:
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
