from __future__ import annotations

from typing import TYPE_CHECKING

from contree_sdk.sdk.objects.subprocess._base import ContreeProcessBase
from contree_sdk.utils.wrapper import coro_sync


if TYPE_CHECKING:
    from contree_sdk.sdk.objects.image_like._sync import _ImageLikeSync


class ContreeProcessSync(ContreeProcessBase):
    def __init__(self, image: _ImageLikeSync, check: bool):
        super().__init__(image)
        self._check = check

    def wait(self):
        return coro_sync(self._wait())

    pass

    # todo to implement
    # __repr__
    # __enter__
    # __exit__
    # __del__
    # communicate
    # kill
    # pid
    # poll
    # send_signal
    # stdin
    # terminate
