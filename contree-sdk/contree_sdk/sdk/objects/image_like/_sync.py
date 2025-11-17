from typing import Self

from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase


class _ImageLikeSync(_ImageLikeBase):
    def wait(self) -> Self:
        pass
