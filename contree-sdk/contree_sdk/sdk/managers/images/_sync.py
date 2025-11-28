from uuid import UUID

from contree_sdk.sdk.managers.images._base import _ImagesBaseManager
from contree_sdk.sdk.objects.image._sync import ContreeImageSync
from contree_sdk.utils.wrapper import coro_sync


class ImagesManagerSync(_ImagesBaseManager[ContreeImageSync]):
    _ImageType = ContreeImageSync

    def __call__(self, *args, **kwargs) -> list[ContreeImageSync]:
        return coro_sync(self._get_images())

    def __iter__(self):
        yield from self()

    def pull(
        self,
        url_or_tag_or_uuid: str | UUID,
        *,
        new_tag: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> ContreeImageSync:
        return coro_sync(self._pull_image(url_or_tag_or_uuid, new_tag=new_tag, username=username, password=password))
