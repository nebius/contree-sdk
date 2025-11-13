from contree_sdk.sdk.managers.base import BaseManager


class _ImagesBaseManager(BaseManager):
    async def _get_images(self): ...  # todo

    async def _pull_image(self): ...  # todo
