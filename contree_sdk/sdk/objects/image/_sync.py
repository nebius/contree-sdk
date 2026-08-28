from contree_sdk.sdk.objects.image._base import ContreeImageBase
from contree_sdk.sdk.objects.image_like._sync import ImageLikeSync
from contree_sdk.sdk.objects.session._sync import ContreeSessionSync


class ContreeImageSync(ContreeImageBase, ImageLikeSync):
    def session(self) -> ContreeSessionSync:
        return ContreeSessionSync(self)
