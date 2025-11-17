from dataclasses import dataclass

from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase


@dataclass
class _ContreeImageBase(_ImageLikeBase): ...
