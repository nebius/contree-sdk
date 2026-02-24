from contree_sdk._internals.utils.typing import keep_signature
from contree_sdk.sdk.client._base import _ContreeBase
from contree_sdk.sdk.managers.files._sync import FilesManagerSync
from contree_sdk.sdk.managers.images._sync import ImagesManagerSync


class ContreeSync(_ContreeBase):
    """Synchronous ConTree SDK client."""

    images: ImagesManagerSync
    files: FilesManagerSync

    @keep_signature(_ContreeBase.__init__)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.images = ImagesManagerSync(client=self)
        self.files = FilesManagerSync(client=self)
