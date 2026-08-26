from contree_sdk.sdk.objects.image_like._async import ImageLikeAsync
from contree_sdk.sdk.objects.session._base import ContreeSessionBase


class ContreeSession(ContreeSessionBase, ImageLikeAsync): ...
