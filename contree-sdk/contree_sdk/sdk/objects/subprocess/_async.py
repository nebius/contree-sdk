from contree_sdk.sdk.objects.image_like._sync import _ImageLikeSync
from contree_sdk.sdk.objects.subprocess._base import ContreeProcessBase


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
