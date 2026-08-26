from contree_sdk.sdk.objects.image._base import ContreeImageBase
from contree_sdk.sdk.objects.image_like._async import ImageLikeAsync
from contree_sdk.sdk.objects.session._async import ContreeSession


class ContreeImage(ContreeImageBase, ImageLikeAsync):
    def session(self) -> ContreeSession:
        return ContreeSession(self)
