from typing import Generic, TypeVar

from contree_sdk.sdk.exceptions.image import ContreeImageNotFound
from contree_sdk.sdk.managers.base import BaseManager
from contree_sdk.sdk.objects.image._base import _ContreeImageBase


_ImageT = TypeVar("_ImageT", bound=_ContreeImageBase)


class _ImagesBaseManager(BaseManager, Generic[_ImageT]):
    _ImageType: type[_ImageT]

    async def _get_images(self) -> list[_ImageT]:
        images = []
        for image in await self._client._api.get_images():
            images.append(
                self._ImageType(
                    client=self._client,
                    uuid=image.uuid,
                    tag=image.tag,
                )
            )
        return images

    # todo add support for __iter__ and __aiter__

    async def _pull_image(self, url_or_tag_or_uuid: str) -> _ImageT:
        return await self._get_image_by_uuid_or_tag(url_or_tag_or_uuid)

    async def _get_image_by_uuid_or_tag(self, uuid_or_tag: str) -> _ImageT:
        # todo replace with actual implementation once api is ready
        images = await self._get_images()
        for image in images:
            if str(image.uuid) == uuid_or_tag or (image.tag and image.tag == uuid_or_tag):
                return image
        raise ContreeImageNotFound(uuid_or_tag)

    async def _import_image(self, image_url: str): ...
