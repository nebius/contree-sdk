from __future__ import annotations

from asyncio import create_task, gather, to_thread
from collections.abc import AsyncIterator, Sequence
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Literal, TypeVar, cast
from uuid import UUID

from contree_client.models import FileSpec, GrepResult

from contree_sdk.sdk.exceptions import ContreeError
from contree_sdk.sdk.io.wiring import OperationOutputs, read_stdin
from contree_sdk.sdk.objects.image_fs._async import ImageDirectory, ImageFile
from contree_sdk.sdk.objects.image_like._base import DirTypeT, FileTypeT, ImageLikeBase
from contree_sdk.sdk.objects.image_like.result import ContreeResult, extract_operation_cost
from contree_sdk.sdk.objects.image_like.state import Executing, Failed, ImageState, Prepared, Succeeded
from contree_sdk.sdk.objects.image_like.waiter_async import OperationWaiter
from contree_sdk.sdk.objects.image_like.waiter_common import MAIN_SPID, OutputChunk
from contree_sdk.utils.models.file import UploadedFile, UploadFileSpec
from contree_sdk.utils.sentinels import value_or_none


ImageLikeAsyncT = TypeVar("ImageLikeAsyncT", bound="ImageLikeAsync")
FilesArg = list[str | Path | UploadFileSpec] | dict[str, str | Path | bytes | UploadFileSpec]


class ImageLikeAsync(ImageLikeBase):
    """Asynchronous image-like object for command execution.

    Every I/O method here calls `self.client.api` (a
    `contree_client.base.ContreeAsyncClient`) directly -- no shared
    coroutine with the sync side, no background event loop.
    """

    def __await__(self):
        return self.wait().__await__()

    def __aiter__(self) -> AsyncIterator[OutputChunk]:
        return self.iter_output()

    async def start(self: ImageLikeAsyncT) -> ImageLikeAsyncT:
        """Start the prepared command without waiting for completion.

        Returns:
            New image instance in EXECUTING state; await it or iterate its
            output chunks to get the result.

        """
        req = self.ensure_state(Prepared).request

        outputs = OperationOutputs.from_request(req)
        files, stdin = await gather(self.prepare_files_for_api(req.files), read_stdin(req.stdin))

        timeout = req.timeout
        if timeout is None:
            timeout = self.client.operation_run_timeout or self.client.operation_timeout

        response = await self.client.api.spawn_instance(
            req.command,
            f"tag:{self.tag}" if self.uuid is None else str(self.uuid),
            hostname=req.hostname or "localhost",
            args=req.args or [],
            env=req.env,
            shell=bool(req.shell),
            cwd=req.cwd or "",
            disposable=req.disposable,
            timeout=round(timeout),
            stdin=stdin,
            files=files,
            truncate_output_at=req.truncate_output_at or self.client.default_truncate_output_at,
            preserve_env=req.preserve_env,
        )
        operation_id = str(response.uuid)
        waiter = OperationWaiter(self.client.api, operation_id)
        for stream_name, output in (("stdout", outputs.stdout), ("stderr", outputs.stderr)):
            if output is not None:
                await waiter.connect_output(output=output, spid=MAIN_SPID, stream_name=stream_name)
        return self.copy_with_state(Executing(request=req, waiter=waiter, outputs=outputs, timeout=timeout))

    async def ensure_started(self: ImageLikeAsyncT) -> tuple[ImageLikeAsyncT, Executing]:
        new_self = self
        if new_self.state == ImageState.PREPARED:
            new_self = await new_self.start()
        return new_self, new_self.ensure_state(Executing)

    async def wait(self: ImageLikeAsyncT) -> ImageLikeAsyncT:
        """Execute the prepared command and wait for completion.

        Returns:
            New image instance with execution results.

        """
        new_self, executing = await self.ensure_started()
        return await new_self.collect_result(executing)

    async def collect_result(self: ImageLikeAsyncT, executing: Executing) -> ImageLikeAsyncT:
        try:
            operation_data, process_result = await executing.waiter.wait_for_result(timeout=executing.timeout)
        except ContreeError:
            if self.state_data is executing:
                self.set_state(Failed(request=executing.request))
            raise

        if self.state_data is not executing:
            return self

        view = executing.waiter.process_view()
        finalized = executing.outputs.finalize(view)
        result = ContreeResult.from_result(
            process_result,
            stdout=finalized.stdout,
            stderr=finalized.stderr,
            truncated=view.truncated,
            cost=extract_operation_cost(operation_data),
        )
        self.set_state(Succeeded(request=executing.request, result=result))
        new_uuid = value_or_none(operation_data.result_image_uuid)
        self.uuid = UUID(new_uuid) if new_uuid else None
        self.tag = None
        if executing.request.tag:
            return await self.tag_as(executing.request.tag)
        return self

    async def iter_output(self) -> AsyncIterator[OutputChunk]:
        new_self, executing = await self.ensure_started()
        result_task = create_task(new_self.collect_result(executing))
        try:
            async for chunk in executing.waiter.iter_chunks(MAIN_SPID):
                yield chunk
            await result_task
        finally:
            if not result_task.done():
                result_task.cancel()
                await gather(result_task, return_exceptions=True)

    # inspect methods

    async def image_uuid(self) -> str:
        if self.uuid is not None:
            return str(self.uuid)
        return await self.client.api.inspect_find_image_by_tag(self.tag or "")

    async def list_entries(
        self, path: str | PurePosixPath, file_type: type[FileTypeT], dir_type: type[DirTypeT]
    ) -> list[FileTypeT | DirTypeT]:
        uuid = await self.image_uuid()
        listing = await self.client.api.inspect_image_list(uuid, str(path))
        result = []
        for item in listing.files:
            type_ = dir_type if item.is_dir else file_type
            result.append(type_(image=self, base_path=PurePosixPath(path), **asdict(item)))
        return result

    async def ls(self, path: str | PurePosixPath = "/") -> list[ImageFile | ImageDirectory]:
        """List files and directories at the given path.

        Args:
            path: Path inside the image to list.

        Returns:
            List of ImageFile and ImageDirectory objects.

        """
        return await self.list_entries(path, ImageFile, ImageDirectory)

    async def read(self, image_path: str | PurePosixPath) -> bytes:
        """Read file contents from the image.

        Args:
            image_path: Path to the file inside the image.

        Returns:
            File contents as bytes.

        """
        uuid = await self.image_uuid()
        return await self.client.api.inspect_image_download(uuid, str(image_path))

    async def download(self, image_path: str | PurePosixPath, local_path: str | Path | None = None) -> Path:
        """Download a file from the image to local filesystem.

        Streams the file directly to disk instead of buffering it in memory.

        Args:
            image_path: Path to the file inside the image.
            local_path: Local destination path. Defaults to filename from image_path.

        Returns:
            Path to the downloaded file.

        """
        image_path = PurePosixPath(image_path)
        if local_path is None:
            local_path = image_path.name
        uuid = await self.image_uuid()
        local_path = Path(local_path)
        file = cast(BinaryIO, await to_thread(local_path.open, "wb"))
        try:
            async for chunk in self.client.api.inspect_image_download_stream(uuid, str(image_path)):
                await to_thread(file.write, chunk)
        finally:
            await to_thread(file.close)
        return local_path

    async def grep(
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
        """Search file contents in the image.

        Args:
            pattern: Search pattern or patterns.
            path: Path or paths to search. Defaults to the image root.
            glob: Glob filter or filters.
            max_count: Maximum matches per file.
            max_total: Maximum matches across all files.
            case: Case matching mode.
            before: Number of context lines before each match.
            after: Number of context lines after each match.

        Returns:
            Typed grep result with matches and truncation status.

        """
        uuid = await self.image_uuid()
        return await self.client.api.inspect_image_grep(
            uuid,
            pattern,
            path=path,
            glob=glob,
            max_count=max_count,
            max_total=max_total,
            case=case,
            before=before,
            after=after,
        )

    async def tag_as(self: ImageLikeAsyncT, tag: str | None) -> ImageLikeAsyncT:
        """Tag this image with the specified tag, or remove the tag if None.

        Args:
            tag: Tag name to apply to the image, or None to remove the tag.

        Returns:
            New instance with updated tag.

        """
        if tag is None:
            return await self.untag()
        await self.client.api.update_image_tag(str(self.uuid), tag)
        new_self = self.copy_self()
        new_self.tag = tag
        return new_self

    async def untag(self: ImageLikeAsyncT) -> ImageLikeAsyncT:
        """Remove the tag from this image.

        Returns:
            New instance with tag set to None.

        """
        await self.client.api.delete_image_tag(str(self.uuid))
        new_self = self.copy_self()
        new_self.tag = None
        return new_self

    async def apply_files(
        self: ImageLikeAsyncT,
        *args: str | Path | UploadFileSpec | FilesArg,
        files: FilesArg | None = None,
    ) -> ImageLikeAsyncT:
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
                prepared_files.extend(UploadFileSpec.prepare_files(arg))
            else:
                prepared_files.append(arg)

        return await self.run(
            shell="true",
            files=(prepared_files + (UploadFileSpec.prepare_files(files) if files else [])),
            disposable=False,
        ).wait()

    async def prepare_files_for_api(self, files: list[UploadFileSpec]) -> dict[str, FileSpec]:
        async def upload_one(file: UploadFileSpec) -> tuple[str, FileSpec]:
            source = file.source
            if isinstance(source, bytes):
                uploaded = await self.client.files.upload_bytes_file(source)
            elif isinstance(source, UploadedFile):
                uploaded = source
            else:
                uploaded = await self.client.files.upload_file(source)
            return str(file.path), FileSpec(uuid=uploaded.uuid, mode=f"{file.mode:04o}", uid=file.uid, gid=file.gid)

        # `return_exceptions=True` so one failing upload doesn't cancel its
        # siblings and leave their exceptions never retrieved; re-raise the
        # first failure once all uploads have settled.
        results = await gather(*(upload_one(i) for i in files), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
        return dict(cast("list[tuple[str, FileSpec]]", results))
