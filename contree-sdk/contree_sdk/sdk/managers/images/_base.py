from typing import Generic, TypeVar

from contree_sdk.sdk.managers.base import BaseManager
from contree_sdk.sdk.objects.image._base import _ContreeImageBase


_ImageT = TypeVar("_ImageT", bound=_ContreeImageBase)


class _ImagesBaseManager(BaseManager, Generic[_ImageT]):
    _ImageType: type[_ImageT]

    async def _get_images(self) -> list[_ImageT]:
        # todo return real sdk objects, not api objects
        return await self._client._api.get_images()

    async def _pull_image(self) -> _ImageT: ...

    async def _get_image_by_uuid_or_tag(self, uuid_or_tag: str): ...

    async def _import_image(self, image_url: str): ...
