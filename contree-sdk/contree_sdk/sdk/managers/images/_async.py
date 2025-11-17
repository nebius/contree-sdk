from contree_sdk.sdk.managers.images._base import _ImagesBaseManager
from contree_sdk.sdk.objects.image._async import ContreeImage


class ImagesManager(_ImagesBaseManager[ContreeImage]):
    _ImageType = ContreeImage

    async def __call__(self, *args, **kwargs) -> list[ContreeImage]:
        return await self._get_images(*args, **kwargs)
