from uuid import UUID

from contree_sdk._internals.utils.deprecation import deprecated
from contree_sdk._internals.utils.typing import keep_signature
from contree_sdk.sdk.managers.images._base import _ImagesBaseManager
from contree_sdk.sdk.objects.image import ContreeImage


class ImagesManager(_ImagesBaseManager[ContreeImage]):
    _ImageType = ContreeImage

    @keep_signature(_ImagesBaseManager[ContreeImage]._get_images)
    async def __call__(self, *args, **kwargs) -> list[ContreeImage]:
        return await self._get_images(*args, **kwargs)

    async def __aiter__(self):
        async for image in self._iter():
            yield image

    @keep_signature(_ImagesBaseManager[ContreeImage]._use_image)
    async def use(self, *args, **kwargs) -> ContreeImage:
        return await self._use_image(*args, **kwargs)

    @deprecated("Use use() or oci() instead")
    async def pull(
        self,
        url_or_tag_or_uuid: str | UUID,
        *,
        new_tag: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> ContreeImage:
        return await self._pull_image(
            url_or_tag_or_uuid, new_tag=new_tag, username=username, password=password, timeout=timeout
        )
