from contree_sdk.sdk.objects.image._base import _ContreeImageBase
from contree_sdk.sdk.objects.image_like._sync import _ImageLikeSync
from contree_sdk.sdk.objects.session._sync import ContreeSessionSync


class ContreeImageSync(_ContreeImageBase, _ImageLikeSync):
    def session(self) -> ContreeSessionSync:
        return ContreeSessionSync(self)
