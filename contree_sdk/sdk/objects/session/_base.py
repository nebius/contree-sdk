from __future__ import annotations

from typing import TypeVar

from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase


_T = TypeVar("_T", bound="_ContreeSessionBase")


class _ContreeSessionBase(_ImageLikeBase):
    def __init__(self, image: _ImageLikeBase):
        super().__init__(image._client, image.uuid, image.tag)

    def _copy_self(self: _T, *_, **__) -> _T:
        return self
