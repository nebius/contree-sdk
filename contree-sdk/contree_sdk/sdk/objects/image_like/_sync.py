from typing import Self

from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase
from contree_sdk.utils.wrapper import coro_sync


class _ImageLikeSync(_ImageLikeBase):
    def wait(self) -> Self:
        return coro_sync(self._await())

    def ls(self, path: str = "/"):
        return coro_sync(self._ls(path))
