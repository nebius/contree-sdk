from pathlib import Path
from typing import Self

from contree_sdk._internals.utils.wrapper import coro_sync
from contree_sdk.sdk.objects.image_fs._sync import ImageDirectorySync, ImageFileSync
from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase
from contree_sdk.sdk.objects.subprocess import ContreeProcessSync
from contree_sdk.utils.io_wrap import IO_TYPES


class _ImageLikeSync(_ImageLikeBase):
    def wait(self) -> Self:
        return coro_sync(self._await())

    def ls(self, path: str | Path = "/") -> list[ImageFileSync | ImageDirectorySync]:
        return coro_sync(self._ls(path, ImageFileSync, ImageDirectorySync))

    def download(self, image_path: str | Path, local_path: str | Path | None = None) -> Path | None:
        return coro_sync(self._download(image_path, local_path))

    # todo move to base, when will implement popen for async
    def popen(
        self,
        args: list[str] | None = None,
        *,
        stdin: IO_TYPES | None = None,
        input: IO_TYPES | None = None,  # noqa: A002
        stdout: IO_TYPES | None = None,
        stderr: IO_TYPES | None = None,
        shell: bool = False,
        cwd: str | None = None,
        timeout: float | None = None,
        check: bool = False,
        text: bool | None = None,
        env: dict[str, str] | None = None,
    ) -> ContreeProcessSync:
        run_params = {}
        if shell:
            run_params["shell"] = args
        elif args:
            run_params["command"], *run_params["args"] = args

        output_type = str if text else text

        return ContreeProcessSync(
            self.run(
                stdin=input or stdin,
                cwd=cwd,
                env=env,
                timeout=timeout,
                stdout=stdout or output_type,
                stderr=stderr or output_type,
                **run_params,
            ),
            check=check,
        )
