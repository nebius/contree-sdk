from contree_sdk.sdk.objects.image_like._async import _ImageLike
from contree_sdk.sdk.objects.session._base import _ContreeSessionBase


class ContreeSession(_ContreeSessionBase, _ImageLike): ...
