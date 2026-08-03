from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import TypeVar

from contree_sdk._internals.io.operation_waiter import OutputChunk
from contree_sdk._internals.io.typing import INPUT_TYPES, OUTPUT_REQUEST_TYPES
from contree_sdk._internals.utils.typing import keep_signature
from contree_sdk._internals.utils.wrapper import coro_iter_sync, coro_sync
from contree_sdk.sdk.objects.image_fs._sync import ImageDirectorySync, ImageFileSync
from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase
from contree_sdk.sdk.objects.subprocess import ContreeProcessSync


_T = TypeVar("_T", bound="_ImageLikeSync")


class _ImageLikeSync(_ImageLikeBase):
    """Synchronous image-like object for command execution."""

    def wait(self: _T) -> _T:
        """Execute the prepared command and wait for completion.

        Returns:
            New image instance with execution results.

        """
        return coro_sync(self._await())

    def __iter__(self) -> Iterator[OutputChunk]:
        return coro_iter_sync(self._iter_output())

    @keep_signature(_ImageLikeBase._start)
    def start(self: _T) -> _T:
        return coro_sync(self._start())

    def ls(self, path: str | PurePosixPath = "/") -> list[ImageFileSync | ImageDirectorySync]:
        """List files and directories at the given path.

        Args:
            path: Path inside the image to list.

        Returns:
            List of ImageFileSync and ImageDirectorySync objects.

        """
        return coro_sync(self._ls(path, ImageFileSync, ImageDirectorySync))

    def download(self, image_path: str | PurePosixPath, local_path: str | Path | None = None) -> Path | None:
        """Download a file from the image to local filesystem.

        Args:
            image_path: Path to the file inside the image.
            local_path: Local destination path. Defaults to filename from image_path.

        Returns:
            Path to the downloaded file.

        """
        return coro_sync(self._download(image_path, local_path))

    def read(self, image_path: str | PurePosixPath) -> bytes:
        """Read file contents from the image.

        Args:
            image_path: Path to the file inside the image.

        Returns:
            File contents as bytes.

        """
        return coro_sync(self._read_file(image_path))

    # todo move to base, when will implement popen for async
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

    @keep_signature(_ImageLikeBase._tag_as)
    def tag_as(self: _T, tag: str | None) -> _T:
        return coro_sync(self._tag_as(tag))

    @keep_signature(_ImageLikeBase._untag)
    def untag(self: _T) -> _T:
        return coro_sync(self._untag())

    @keep_signature(_ImageLikeBase._apply_files)
    def apply_files(self: _T, *args, **kwargs) -> _T:
        return coro_sync(self._apply_files(*args, **kwargs))
