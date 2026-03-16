from contree_sdk._internals.utils.typing import keep_signature
from contree_sdk.sdk.client._base import _ContreeBase
from contree_sdk.sdk.managers.files._async import FilesManager
from contree_sdk.sdk.managers.images._async import ImagesManager
from contree_sdk.utils.models.auth import WhoAmI


class Contree(_ContreeBase):
    """Asynchronous ConTree SDK client."""

    files: FilesManager
    images: ImagesManager

    @keep_signature(_ContreeBase.__init__)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.images = ImagesManager(client=self)
        self.files = FilesManager(client=self)

    async def get_token_info(self, refresh: bool = False) -> WhoAmI:
        return await self._get_token_info(refresh=refresh)
