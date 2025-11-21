from functools import wraps

from contree_sdk.sdk.client._base import _ContreeBase
from contree_sdk.sdk.managers.files._async import FilesManager
from contree_sdk.sdk.managers.images._async import ImagesManager


class Contree(_ContreeBase):
    files: FilesManager
    images: ImagesManager

    @wraps(_ContreeBase.__init__)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.images = ImagesManager(client=self)
        self.files = FilesManager(client=self)
