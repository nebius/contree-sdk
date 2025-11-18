from contree_sdk.sdk.managers.images._base import _ImagesBaseManager
from contree_sdk.sdk.objects.image._sync import ContreeImageSync
from contree_sdk.utils.wrapper import coro_sync


class ImagesManagerSync(_ImagesBaseManager[ContreeImageSync]):
    _ImageType = ContreeImageSync

    def __call__(self, *args, **kwargs) -> list[ContreeImageSync]:
        return coro_sync(self._get_images())
