from uuid import UUID

from contree_sdk._internals.utils.wrapper import coro_iter_sync, coro_sync
from contree_sdk.sdk.managers.images._base import _ImagesBaseManager
from contree_sdk.sdk.objects.image import ContreeImageSync


class ImagesManagerSync(_ImagesBaseManager[ContreeImageSync]):
    _ImageType = ContreeImageSync

    def __call__(self, *args, **kwargs) -> list[ContreeImageSync]:
        return coro_sync(self._get_images(*args, **kwargs))

    def __iter__(self):
        yield from coro_iter_sync(self._iter())

    def pull(
        self,
        url_or_tag_or_uuid: str | UUID,
        *,
        new_tag: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> ContreeImageSync:
        return coro_sync(self._pull_image(url_or_tag_or_uuid, new_tag=new_tag, username=username, password=password))
