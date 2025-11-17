from contree_sdk.sdk.managers.base import BaseManager


class _ImagesBaseManager(BaseManager):
    async def _get_images(self):
        # todo return real sdk objects, not api objects
        return await self._client._api.get_images()

    async def _pull_image(self): ...  # todo
