from contree_sdk.sdk.objects.image._base import _ContreeImageBase
from contree_sdk.sdk.objects.image_like._async import _ImageLike


class ContreeImage(_ContreeImageBase, _ImageLike):
    async def totally_async(self):
        # marker for me that it's sync
        # todo delete
        ...
