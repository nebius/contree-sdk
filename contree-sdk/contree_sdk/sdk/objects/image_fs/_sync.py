from dataclasses import dataclass

from contree_sdk.sdk.objects.image_fs._base import _ImageDirectoryBase, _ImageFileBase


@dataclass
class ImageFileSync(_ImageFileBase): ...


@dataclass
class ImageDirectorySync(_ImageDirectoryBase): ...
