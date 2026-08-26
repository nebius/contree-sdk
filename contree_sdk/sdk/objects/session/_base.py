from __future__ import annotations

from typing import TypeVar

from contree_sdk.sdk.objects.image_like._base import ImageLikeBase


ContreeSessionT = TypeVar("ContreeSessionT", bound="ContreeSessionBase")


class ContreeSessionBase(ImageLikeBase):
    def __init__(self, image: ImageLikeBase):
        super().__init__(image.client, image.uuid, image.tag)

    def copy_self(self: ContreeSessionT, *_, **__) -> ContreeSessionT:
        return self
