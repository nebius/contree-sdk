from contree_sdk.sdk.objects.image_like._sync import ImageLikeSync
from contree_sdk.sdk.objects.session._base import ContreeSessionBase


class ContreeSessionSync(ContreeSessionBase, ImageLikeSync): ...
