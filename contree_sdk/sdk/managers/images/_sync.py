from uuid import UUID

from contree_sdk._internals.utils.deprecation import deprecated
from contree_sdk._internals.utils.typing import keep_signature
from contree_sdk._internals.utils.wrapper import coro_iter_sync, coro_sync
from contree_sdk.sdk.managers.images._base import _ImagesBaseManager
from contree_sdk.sdk.objects.image import ContreeImageSync


class ImagesManagerSync(_ImagesBaseManager[ContreeImageSync]):
    _ImageType = ContreeImageSync

    @keep_signature(_ImagesBaseManager[ContreeImageSync]._get_images)
    def __call__(self, *args, **kwargs) -> list[ContreeImageSync]:
        return coro_sync(self._get_images(*args, **kwargs))

    def __iter__(self):
        yield from coro_iter_sync(self._iter())

    @keep_signature(_ImagesBaseManager[ContreeImageSync]._use_image)
    def use(self, *args, **kwargs) -> ContreeImageSync:
        return coro_sync(self._use_image(*args, **kwargs))

    @deprecated("Use use() or oci() instead")
    def pull(
        self,
        url_or_tag_or_uuid: str | UUID,
        *,
        new_tag: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> ContreeImageSync:
        return coro_sync(
            self._pull_image(url_or_tag_or_uuid, new_tag=new_tag, username=username, password=password, timeout=timeout)
        )

    @keep_signature(_ImagesBaseManager[ContreeImageSync]._pull_image_by_oci)
    def oci(self, *args, **kwargs) -> ContreeImageSync:
        return coro_sync(self._pull_image_by_oci(*args, **kwargs))

    docker = podman = pull_by_oci = oci

    @keep_signature(_ImagesBaseManager[ContreeImageSync]._import_image)
    def import_from(self, *args, **kwargs) -> ContreeImageSync:
        return coro_sync(self._import_image(*args, **kwargs))
