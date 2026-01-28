from contree_sdk.sdk.objects.image_like._sync import _ImageLikeSync
from contree_sdk.sdk.objects.session._base import _ContreeSessionBase


class ContreeSessionSync(_ContreeSessionBase, _ImageLikeSync): ...
