from contree_sdk.sdk.client.base import _ContreeBase
from contree_sdk.sdk.managers.images.manager import ImagesManager


class Contree(_ContreeBase):
    def __init__(self):
        self.images = ImagesManager(client=self)

    pass
