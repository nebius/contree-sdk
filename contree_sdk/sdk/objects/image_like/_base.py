from __future__ import annotations

from asyncio import create_task, gather, to_thread
from collections.abc import AsyncGenerator, Iterable, Sequence
from contextlib import aclosing
from copy import copy
from dataclasses import replace
from datetime import timedelta
from math import ceil
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, BinaryIO, Literal, TypeVar, cast, overload
from uuid import UUID

from contree_client.models import FileSpec, GrepResult

from contree_sdk._internals.io.operation_waiter import MAIN_SPID, OutputChunk
from contree_sdk._internals.io.typing import INPUT_TYPES, OUTPUT_REQUEST_TYPES, OUTPUT_TYPES
from contree_sdk._internals.io.wiring import OperationOutputs
from contree_sdk.sdk.exceptions import ContreeError, ContreeImageStateError, DisposableImageRunError
from contree_sdk.sdk.objects.image_like.result import ContreeResult
from contree_sdk.sdk.objects.image_like.state import (
    STATE_MACHINE,
    ImageState,
    StateData,
    StateDataT,
    _Executing,
    _Failed,
    _Prepared,
    _Pulled,
    _Succeeded,
    _WithRequest,
)
from contree_sdk.sdk.objects.run import RunRequest
from contree_sdk.utils.models.file import UploadedFile, UploadFileSpec


if TYPE_CHECKING:
    from contree_sdk.sdk.client._base import _ContreeBase

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
        self._state_data: StateData = _Pulled()

    # utils methods

    def _copy_self(self: _T) -> _T:
        return copy(self)

    def _copy_with_state(self: _T, data: StateData) -> _T:
        new_self = self._copy_self()
        new_self._set_state(data)
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
        stdin: INPUT_TYPES | None = None,
        stdout: OUTPUT_REQUEST_TYPES | None = str,
        stderr: OUTPUT_REQUEST_TYPES | None = str,
        tag: str | None = None,
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | bytes | UploadFileSpec] | None = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
        preserve_env: bool = False,
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
        stdin: INPUT_TYPES | None = None,
        stdout: OUTPUT_REQUEST_TYPES | None = str,
        stderr: OUTPUT_REQUEST_TYPES | None = str,
        tag: str | None = None,
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | bytes | UploadFileSpec] | None = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
        preserve_env: bool = False,
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
        stdin: INPUT_TYPES | None = None,
        stdout: OUTPUT_REQUEST_TYPES | None = str,
        stderr: OUTPUT_REQUEST_TYPES | None = str,
        tag: str | None = None,
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | bytes | UploadFileSpec] | None = None,
        timeout: float | timedelta | None = None,
        disposable: bool = True,
        truncate_output_at: int | None = None,
        preserve_env: bool = False,
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
            files=UploadFileSpec._prepare_files(files or []),
            stdout=stdout,
            stderr=stderr,
            disposable=disposable,
            truncate_output_at=truncate_output_at,
            preserve_env=preserve_env,
        )
        return self._copy_with_state(_Prepared(request=request))

    async def _apply_files(
        self: _T,
        *args: str
        | Path
        | UploadFileSpec
        | list[str | Path | UploadFileSpec]
        | dict[str, str | Path | bytes | UploadFileSpec],
        files: list[str | Path | UploadFileSpec] | dict[str, str | Path | bytes | UploadFileSpec] | None = None,
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

    async def _prepare_files_for_api(self, files: list[UploadFileSpec]) -> dict[str, FileSpec]:
        async def _upload_file(file: UploadFileSpec) -> tuple[str, FileSpec]:
            source = file.source
            if isinstance(source, bytes):
                source = await self._client.files._upload_bytes_file(source)
            elif not isinstance(source, UploadedFile):
                source = await self._client.files._upload_file(source)
            return str(file.path), FileSpec(
                uuid=source.uuid,
                mode=f"{file.mode:04o}",
                uid=file.uid,
                gid=file.gid,
            )

        return dict(await gather(*(_upload_file(i) for i in files)))

    def _update_request(self: _T, **kwargs) -> _T:
        prepared = self._ensure_state(_Prepared)
        return self._copy_with_state(_Prepared(request=replace(prepared.request, **kwargs)))

    # internal methods

    def _ensure_state(self, state_type: type[StateDataT]) -> StateDataT:
        data = self._state_data
        if not isinstance(data, state_type):
            raise ContreeImageStateError(image_uuid=self.uuid, state=self.state, states=[state_type.state])
        return data

    def _set_state(self, data: StateData) -> None:
        possible_states = STATE_MACHINE.get(self.state, frozenset())
        if data.state not in possible_states:
            raise ContreeImageStateError(image_uuid=self.uuid, state=self.state, states=list(possible_states))
        self._state_data = data

    @property
    def state(self) -> ImageState:
        """Current state of the image in the execution lifecycle."""
        return self._state_data.state

    async def _start(self: _T) -> _T:
        """Start the prepared command without waiting for completion.

        Returns:
            New image instance in EXECUTING state; await it or iterate its
            output chunks to get the result.

        """
        req = self._ensure_state(_Prepared).request

        outputs = OperationOutputs.from_request(req)
        files, stdin = await gather(self._prepare_files_for_api(req.files), req._read_stdin())

        timeout = req.timeout
        if timeout is None:
            timeout = self._client.config.operation_run_timeout or self._client.config.operation_timeout
        self._client._warn_if_timeout_exceeds_limit(timeout, "instance_max_timeout")

        truncate_output_at = req.truncate_output_at or self._client.config.default_truncate_output_at
        operation_uuid = await self._client._start_spawn(
            command=req.command,
            image=f"tag:{self.tag}" if self.uuid is None else str(self.uuid),
            hostname=req.hostname or "localhost",
            args=req.args or [],
            env=req.env,
            shell=bool(req.shell),
            cwd=req.cwd or "",
            disposable=req.disposable,
            timeout=round(timeout),
            stdin=stdin,
            files=files,
            truncate_output_at=truncate_output_at,
            preserve_env=req.preserve_env,
        )
        waiter = await self._client._get_operation_waiter(operation_uuid)
        waiter._set_output_limit(truncate_output_at)
        await outputs.connect(waiter)
        return self._copy_with_state(_Executing(request=req, waiter=waiter, outputs=outputs, timeout=timeout))

    async def _ensure_started(self: _T) -> tuple[_T, _Executing]:
        new_self = self
        if new_self.state == ImageState.PREPARED:
            new_self = await new_self._start()
        return new_self, new_self._ensure_state(_Executing)

    async def _await(self: _T) -> _T:
        new_self, executing = await self._ensure_started()
        return await new_self._collect_result(executing)

    async def _collect_result(self: _T, executing: _Executing) -> _T:
        try:
            operation_data, process_result = await executing.waiter.wait_for_result(operation_timeout=executing.timeout)
        except ContreeError:
            if self._state_data is executing:
                self._set_state(_Failed(request=executing.request))
                executing.outputs.close()
            raise

        if self._state_data is not executing:
            return self

        cost = await self._client._get_compat_operation_cost(executing.waiter.operation_id)
        view = executing.waiter.process_view()
        finalized = executing.outputs.finalize(view)
        result = ContreeResult.from_result(
            process_result,
            stdout=finalized.stdout,
            stderr=finalized.stderr,
            truncated=view.truncated,
            cost=cost,
        )
        self._set_state(_Succeeded(request=executing.request, result=result))
        new_uuid = operation_data.result_image_uuid
        self.uuid = UUID(new_uuid) if isinstance(new_uuid, str) else None
        self.tag = None
        if executing.request.tag:
            return await self._tag_as(executing.request.tag)
        return self

    async def _iter_output(self) -> AsyncGenerator[OutputChunk]:
        new_self, executing = await self._ensure_started()
        result_task = create_task(new_self._collect_result(executing))
        try:
            async for chunk in executing.waiter.iter_chunks(MAIN_SPID):
                yield chunk
            await result_task
        finally:
            if not result_task.done():
                result_task.cancel()
                await gather(result_task, return_exceptions=True)

    # inspect methods

    async def _resolved_uuid(self) -> str:
        if self.uuid is not None:
            return str(self.uuid)
        return await self._client._api.inspect_find_image_by_tag(self.tag or "")

    async def _ls(
        self, path: str | PurePosixPath, file_type: type[FileTypeT], dir_type: type[DirTypeT]
    ) -> list[FileTypeT | DirTypeT]:
        listing = await self._client._api.inspect_image_list(await self._resolved_uuid(), str(path))
        result = []
        for obj in listing.files:
            type_ = dir_type if obj.is_dir else file_type
            result.append(
                type_(
                    _image=self,
                    _path=PurePosixPath(path),
                    **obj.to_dict(),
                )
            )
        return result

    async def _grep(
        self,
        pattern: str | Sequence[str],
        *,
        path: str | Sequence[str] | None = None,
        glob: str | Sequence[str] | None = None,
        max_count: int | None = None,
        max_total: int | None = None,
        case: Literal["sensitive", "insensitive", "smart"] | None = None,
        before: int | None = None,
        after: int | None = None,
    ) -> GrepResult:
        return await self._client._api.inspect_image_grep(
            await self._resolved_uuid(),
            pattern,
            path=path,
            glob=glob,
            max_count=max_count,
            max_total=max_total,
            case=case,
            before=before,
            after=after,
        )

    async def _read_file(self, path: str | PurePosixPath) -> bytes:
        return await self._client._api.inspect_image_download(await self._resolved_uuid(), str(path))

    async def _download(self, image_path: str | PurePosixPath, local_path: str | Path | None = None) -> Path:
        image_path = PurePosixPath(image_path)
        if local_path is None:
            local_path = image_path.name
        file = cast(BinaryIO, await to_thread(open, local_path, "wb"))
        with file:
            chunks = self._client._api.inspect_image_download_stream(await self._resolved_uuid(), str(image_path))
            async with aclosing(chunks):
                async for chunk in chunks:
                    await to_thread(file.write, chunk)
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
        """Execution result. Only available after successful execution."""
        return self._ensure_state(_Succeeded).result

    @property
    def _request(self) -> RunRequest | None:
        data = self._state_data
        return data.request if isinstance(data, _WithRequest) else None

    @property
    def stdin(self) -> INPUT_TYPES | None:
        """Configured stdin source."""
        return self._request.stdin if self._request else None

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

    async def _tag_as(self: _T, tag: str | None) -> _T:
        """Tag this image with the specified tag, or remove the tag if None.

        Args:
            tag: Tag name to apply to the image, or None to remove the tag.

        Returns:
            New instance with updated tag.

        """
        if tag is None:
            return await self._untag()
        await self._client._api.update_image_tag(str(self.uuid), tag)
        new_self = self._copy_self()
        new_self.tag = tag
        return new_self

    async def _untag(self: _T) -> _T:
        """Remove the tag from this image.

        Returns:
            New instance with tag set to None.

        """
        await self._client._api.delete_image_tag(str(self.uuid))
        new_self = self._copy_self()
        new_self.tag = None
        return new_self

    @property
    def client(self):
        return self._client
