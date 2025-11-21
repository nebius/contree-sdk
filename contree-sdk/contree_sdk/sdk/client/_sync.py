from functools import wraps

from contree_sdk.sdk.client._base import _ContreeBase
from contree_sdk.sdk.managers.files._sync import FilesManagerSync
from contree_sdk.sdk.managers.images._sync import ImagesManagerSync


class ContreeSync(_ContreeBase):
    images: ImagesManagerSync
    files: FilesManagerSync

    @wraps(_ContreeBase.__init__)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.images = ImagesManagerSync(client=self)
        self.files = FilesManagerSync(client=self)
