from __future__ import annotations

from typing import TYPE_CHECKING

from contree_sdk.sdk.objects.subprocess._base import ContreeProcessBase


if TYPE_CHECKING:
    from contree_sdk.sdk.objects.image_like._sync import _ImageLikeSync


class ContreeProcess(ContreeProcessBase):
    def __init__(self, image: _ImageLikeSync):
        super().__init__(image)

    pass
    # todo to implement
    # __aenter__
    # __aexit__
    # __repr__
    # communicate
    # kill
    # pid
    # send_signal
    # stdin
    # terminate
    # wait
