from __future__ import annotations

from datetime import timedelta
from subprocess import CalledProcessError
from typing import TYPE_CHECKING

from contree_sdk.sdk.objects.subprocess._base import ContreeProcessBase


if TYPE_CHECKING:
    from contree_sdk.sdk.objects.image_like._sync import ImageLikeSync


class ContreeProcessSync(ContreeProcessBase):
    # narrows the base's `image: ImageLikeBase` -- `wait()`/`request` etc.
    # only exist on the sync variant, not the shared base
    image: ImageLikeSync

    def __init__(self, image: ImageLikeSync, check: bool):
        super().__init__(image, check=check)

    def wait(self) -> None:
        self.image = self.image.wait()
        if self.check and self.returncode != 0:
            req = self.image.request
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

    def communicate(self, input: str | bytes | None = None, timeout: float | timedelta | None = None):  # noqa: A002
        self.image = self.image.update_request(stdin=input, timeout=timeout)
        self.image = self.image.wait()
        return self.stdout, self.stderr

    # todo to implement
    # kill
    # pid
    # poll
    # send_signal
    # terminate
