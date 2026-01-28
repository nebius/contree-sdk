from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from contree_sdk._internals.utils.wrapper import coro_sync
from contree_sdk.sdk.objects.subprocess._base import ContreeProcessBase


if TYPE_CHECKING:
    from contree_sdk.sdk.objects.image_like._sync import _ImageLikeSync


class ContreeProcessSync(ContreeProcessBase):
    def __init__(self, image: _ImageLikeSync, check: bool):
        super().__init__(image, check=check)

    def wait(self) -> None:
        return coro_sync(self._wait())

    def communicate(self, input: str | bytes | None = None, timeout: float | timedelta | None = None):  # noqa: A002
        return coro_sync(self._communicate(input=input, timeout=timeout))

    # todo to implement
    # kill
    # pid
    # poll
    # send_signal
    # terminate
