from contree_sdk.sdk.objects.image._base import _ContreeImageBase
from contree_sdk.sdk.objects.image_like._sync import _ImageLikeSync


class ContreeImageSync(_ContreeImageBase, _ImageLikeSync): ...
