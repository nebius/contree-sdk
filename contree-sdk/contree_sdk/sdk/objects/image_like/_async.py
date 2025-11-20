from contree_sdk.sdk.objects.image_like._base import _ImageLikeBase


class _ImageLike(_ImageLikeBase):
    def __await__(self):
        return self._await().__await__()

    ls = _ImageLikeBase._ls
