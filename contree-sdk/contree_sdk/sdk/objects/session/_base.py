from typing import Self

from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase


class _ContreeSessionBase(_ImageLikeBase):
    def __init__(self, image: _ImageLikeBase):
        super().__init__(image._client, image.uuid, image.tag)

    def _copy_self(self, *_) -> Self:
        return self
