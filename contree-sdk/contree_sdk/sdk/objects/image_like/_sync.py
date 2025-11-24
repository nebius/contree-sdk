from typing import Self

from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase
from contree_sdk.sdk.objects.subprocess import ContreeProcessSync
from contree_sdk.utils.wrapper import coro_sync


class _ImageLikeSync(_ImageLikeBase):
    def wait(self) -> Self:
        return coro_sync(self._await())

    def ls(self, path: str = "/"):
        return coro_sync(self._ls(path))

    # todo move to base, when will implement popen for async
    def popen(
        self,
        args=None,
        *,
        stdin=None,
        input=None,  # noqa: A002
        stdout=None,
        stderr=None,
        shell=False,
        cwd=None,
        timeout=None,
        check=False,
        text=None,  # todo support it
        env=None,
    ) -> ContreeProcessSync:
        run_params = {}
        if shell:
            run_params["shell"] = args
        elif args:
            run_params["command"], *run_params["args"] = args

        return ContreeProcessSync(
            self.run(
                stdin=input or stdin,
                cwd=cwd,
                env=env,
                timeout=timeout,
                stdout=stdout,
                stderr=stderr,
                **run_params,
            ),
            check=check,
        )
