from contree_sdk.sdk.objects.image._base import _ContreeImageBase
from contree_sdk.sdk.objects.image_like._async import _ImageLike


class ContreeImage(_ContreeImageBase, _ImageLike): ...
