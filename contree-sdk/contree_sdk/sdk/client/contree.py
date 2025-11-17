from functools import wraps

from contree_sdk.sdk.client.base import _ContreeBase
from contree_sdk.sdk.managers.images._async import ImagesManager


class Contree(_ContreeBase):
    @wraps(_ContreeBase.__init__)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.images = ImagesManager(client=self)
