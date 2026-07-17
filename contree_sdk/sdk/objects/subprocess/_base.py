from datetime import timedelta
from subprocess import CalledProcessError

from contree_sdk._internals.io.typing import INPUT_TYPES, OUTPUT_TYPES
from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase


class ContreeProcessBase:
    def __init__(self, image: _ImageLikeBase, check: bool):
        self._image = image
        self._check = check

    @property
    def stdin(self) -> INPUT_TYPES | None:
        return self._image.stdin

    @property
    def stdout(self) -> OUTPUT_TYPES | None:
        return self._image.stdout

    @property
    def stderr(self) -> OUTPUT_TYPES | None:
        return self._image.stderr

    @property
    def returncode(self) -> int:
        return self._image.exit_code

    async def _wait(self):
        self._image = await self._image._await()
        if self._check and self.returncode != 0:
            req = self._image._request
            if req is None:
                raise RuntimeError("Image is not configured")
            cmd = [req.command]
            if req.args:
                cmd.extend(req.args)
            raise CalledProcessError(
                cmd=cmd,
                returncode=self.returncode,
                output=self.stdout,
                stderr=self.stderr,
            )

    async def _communicate(self, input: str | bytes | None = None, timeout: float | timedelta | None = None):  # noqa: A002
        self._image = self._image._update_request(stdin=input, timeout=timeout)
        self._image = await self._image._await()
        return self.stdout, self.stderr

    def __repr__(self):
        return f"{type(self).__name__}(image={self._image!r})"

    # todo to implement
    # __aenter__
    # __aexit__

    # __repr__
    # kill
    # pid
    # send_signal
    # stdin
    # terminate

    # __enter__
    # __exit__
    # __del__
    # communicate
    # kill
    # pid
    # poll
    # send_signal
    # terminate
