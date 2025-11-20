from contree_sdk.sdk.managers.images._base import _ImagesBaseManager
from contree_sdk.sdk.objects.image._async import ContreeImage


class ImagesManager(_ImagesBaseManager[ContreeImage]):
    _ImageType = ContreeImage

    async def __call__(self, *args, **kwargs) -> list[ContreeImage]:
        return await self._get_images(*args, **kwargs)

    async def __aiter__(self):
        for image in await self():
            yield image

    async def pull(self, url_or_tag_or_uuid: str) -> ContreeImage:
        return await self._pull_image(url_or_tag_or_uuid)
