from pathlib import Path

from contree_sdk.sdk.objects.image_fs._async import ImageDirectory, ImageFile
from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase


class _ImageLike(_ImageLikeBase):
    def __await__(self):
        return self._await().__await__()

    async def ls(self, path: str | Path = "/") -> list[ImageFile | ImageDirectory]:
        return await self._ls(path, ImageFile, ImageDirectory)
