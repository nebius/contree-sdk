from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import asdict
from pathlib import Path, PurePosixPath
from typing import Literal, TypeVar
from uuid import UUID

from contree_client.models import FileSpec, GrepResult

from contree_sdk.sdk.exceptions import ContreeError
from contree_sdk.sdk.io.typing import INPUT_TYPES, OUTPUT_REQUEST_TYPES
from contree_sdk.sdk.io.wiring import OperationOutputs, read_stdin_sync
from contree_sdk.sdk.objects.image_fs._sync import ImageDirectorySync, ImageFileSync
from contree_sdk.sdk.objects.image_like._base import DirTypeT, FileTypeT, ImageLikeBase
from contree_sdk.sdk.objects.image_like.result import ContreeResult, extract_operation_cost
from contree_sdk.sdk.objects.image_like.state import Executing, Failed, ImageState, Prepared, Succeeded
from contree_sdk.sdk.objects.image_like.waiter_common import MAIN_SPID, OutputChunk
from contree_sdk.sdk.objects.image_like.waiter_sync import OperationWaiter
from contree_sdk.sdk.objects.subprocess._sync import ContreeProcessSync
from contree_sdk.utils.models.file import UploadedFile, UploadFileSpec
from contree_sdk.utils.sentinels import value_or_none


ImageLikeSyncT = TypeVar("ImageLikeSyncT", bound="ImageLikeSync")
FilesArg = list[str | Path | UploadFileSpec] | dict[str, str | Path | bytes | UploadFileSpec]


class ImageLikeSync(ImageLikeBase):
    """Synchronous image-like object for command execution.

    Every I/O method here calls `self.client.api` (a
    `contree_client.base.ContreeSyncClient`) directly and blocks -- no
    background event loop, no thread bridging.
    """

    def __iter__(self) -> Iterator[OutputChunk]:
        return self.iter_output()

    def start(self: ImageLikeSyncT) -> ImageLikeSyncT:
        """Start the prepared command without waiting for completion.

        Returns:
            New image instance in EXECUTING state; call wait() or iterate its
            output chunks to get the result.

        """
        req = self.ensure_state(Prepared).request

        outputs = OperationOutputs.from_request(req)
        files = self.prepare_files_for_api(req.files)
        stdin = read_stdin_sync(req.stdin)

        timeout = req.timeout
        if timeout is None:
            timeout = self.client.operation_run_timeout or self.client.operation_timeout

        response = self.client.api.spawn_instance(
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
                waiter.connect_output(output=output, spid=MAIN_SPID, stream_name=stream_name)
        return self.copy_with_state(Executing(request=req, waiter=waiter, outputs=outputs, timeout=timeout))

    def ensure_started(self: ImageLikeSyncT) -> tuple[ImageLikeSyncT, Executing]:
        new_self = self
        if new_self.state == ImageState.PREPARED:
            new_self = new_self.start()
        return new_self, new_self.ensure_state(Executing)

    def wait(self: ImageLikeSyncT) -> ImageLikeSyncT:
        """Execute the prepared command and wait for completion.

        Returns:
            New image instance with execution results.

        """
        new_self, executing = self.ensure_started()
        return new_self.collect_result(executing)

    def collect_result(self: ImageLikeSyncT, executing: Executing) -> ImageLikeSyncT:
        try:
            operation_data, process_result = executing.waiter.wait_for_result(timeout=executing.timeout)
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
            return self.tag_as(executing.request.tag)
        return self

    def iter_output(self) -> Iterator[OutputChunk]:
        new_self, executing = self.ensure_started()
        yield from executing.waiter.iter_chunks(MAIN_SPID, executing.timeout)
        new_self.collect_result(executing)

    # inspect methods

    def image_uuid(self) -> str:
        if self.uuid is not None:
            return str(self.uuid)
        return self.client.api.inspect_find_image_by_tag(self.tag or "")

    def list_entries(
        self, path: str | PurePosixPath, file_type: type[FileTypeT], dir_type: type[DirTypeT]
    ) -> list[FileTypeT | DirTypeT]:
        uuid = self.image_uuid()
        listing = self.client.api.inspect_image_list(uuid, str(path))
        result = []
        for item in listing.files:
            type_ = dir_type if item.is_dir else file_type
            result.append(type_(image=self, base_path=PurePosixPath(path), **asdict(item)))
        return result

    def ls(self, path: str | PurePosixPath = "/") -> list[ImageFileSync | ImageDirectorySync]:
        """List files and directories at the given path.

        Args:
            path: Path inside the image to list.

        Returns:
            List of ImageFileSync and ImageDirectorySync objects.

        """
        return self.list_entries(path, ImageFileSync, ImageDirectorySync)

    def read(self, image_path: str | PurePosixPath) -> bytes:
        """Read file contents from the image.

        Args:
            image_path: Path to the file inside the image.

        Returns:
            File contents as bytes.

        """
        uuid = self.image_uuid()
        return self.client.api.inspect_image_download(uuid, str(image_path))

    def download(self, image_path: str | PurePosixPath, local_path: str | Path | None = None) -> Path:
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
        uuid = self.image_uuid()
        with Path(local_path).open("wb") as file:
            for chunk in self.client.api.inspect_image_download_stream(uuid, str(image_path)):
                file.write(chunk)
        return Path(local_path)

    def grep(
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
        uuid = self.image_uuid()
        return self.client.api.inspect_image_grep(
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

    def popen(
        self,
        args: list[str] | str | None = None,
        *,
        stdin: INPUT_TYPES | None = None,
        input: INPUT_TYPES | None = None,  # noqa: A002
        stdout: OUTPUT_REQUEST_TYPES | None = None,
        stderr: OUTPUT_REQUEST_TYPES | None = None,
        shell: bool = False,
        cwd: str | None = None,
        timeout: float | None = None,
        check: bool = False,
        text: bool | None = None,
        env: dict[str, str] | None = None,
    ) -> ContreeProcessSync:
        """Run a command with subprocess-like interface.

        Args:
            args: Command and arguments list.
            stdin: Input source.
            input: Alternative input source (alias for stdin).
            stdout: Output destination for stdout.
            stderr: Output destination for stderr.
            shell: If True, treat args as shell command.
            cwd: Working directory inside the image.
            timeout: Execution timeout in seconds.
            check: If True, raise on non-zero exit code.
            text: If True, decode output as text.
            env: Environment variables.

        Returns:
            ContreeProcessSync object with execution results.

        """
        run_params = {}
        if shell:
            run_params["shell"] = args
        elif args:
            run_params["command"], *run_params["args"] = args

        output_type = str if text else bytes

        return ContreeProcessSync(
            self.run(  # ty: ignore[no-matching-overload]
                stdin=input or stdin,
                cwd=cwd,
                env=env,
                timeout=timeout,
                stdout=stdout if stdout is not None else output_type,
                stderr=stderr if stderr is not None else output_type,
                **run_params,
            ),
            check=check,
        )

    def tag_as(self: ImageLikeSyncT, tag: str | None) -> ImageLikeSyncT:
        """Tag this image with the specified tag, or remove the tag if None.

        Args:
            tag: Tag name to apply to the image, or None to remove the tag.

        Returns:
            New instance with updated tag.

        """
        if tag is None:
            return self.untag()
        self.client.api.update_image_tag(str(self.uuid), tag)
        new_self = self.copy_self()
        new_self.tag = tag
        return new_self

    def untag(self: ImageLikeSyncT) -> ImageLikeSyncT:
        """Remove the tag from this image.

        Returns:
            New instance with tag set to None.

        """
        self.client.api.delete_image_tag(str(self.uuid))
        new_self = self.copy_self()
        new_self.tag = None
        return new_self

    def apply_files(
        self: ImageLikeSyncT,
        *args: str | Path | UploadFileSpec | FilesArg,
        files: FilesArg | None = None,
    ) -> ImageLikeSyncT:
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

        return self.run(
            shell="true",
            files=(prepared_files + (UploadFileSpec.prepare_files(files) if files else [])),
            disposable=False,
        ).wait()

    def prepare_files_for_api(self, files: list[UploadFileSpec]) -> dict[str, FileSpec]:
        result: dict[str, FileSpec] = {}
        for file in files:
            source = file.source
            if isinstance(source, bytes):
                uploaded = self.client.files.upload_bytes_file(source)
            elif isinstance(source, UploadedFile):
                uploaded = source
            else:
                uploaded = self.client.files.upload_file(source)
            result[str(file.path)] = FileSpec(uuid=uploaded.uuid, mode=f"{file.mode:04o}", uid=file.uid, gid=file.gid)
        return result
