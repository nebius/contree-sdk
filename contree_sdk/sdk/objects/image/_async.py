from contree_sdk.sdk.objects.image._base import _ContreeImageBase
from contree_sdk.sdk.objects.image_like._async import _ImageLike
from contree_sdk.sdk.objects.session._async import ContreeSession


class ContreeImage(_ContreeImageBase, _ImageLike):
    def session(self) -> ContreeSession:
        return ContreeSession(self)
