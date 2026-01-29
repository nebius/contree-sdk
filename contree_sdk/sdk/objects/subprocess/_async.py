from __future__ import annotations

from typing import TYPE_CHECKING

from contree_sdk.sdk.objects.subprocess._base import ContreeProcessBase


if TYPE_CHECKING:
    pass


class ContreeProcess(ContreeProcessBase):
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
