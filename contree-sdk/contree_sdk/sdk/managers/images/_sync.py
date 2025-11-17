import asyncio

from contree_sdk.sdk.managers.images._base import _ImagesBaseManager
from contree_sdk.sdk.objects.image._sync import ContreeImageSync


class ImagesManagerSync(_ImagesBaseManager[ContreeImageSync]):
    _ImageType = ContreeImageSync

    def __call__(self, *args, **kwargs) -> list[ContreeImageSync]:
        # todo to real wrapper
        return asyncio.run(self._get_images())
