from contree_sdk.sdk.objects.image._base import _ContreeImageBase
from contree_sdk.sdk.objects.image_like._sync import _ImageLikeSync
from contree_sdk.sdk.objects.subprocess._sync import ContreeProcessSync


class ContreeImageSync(_ContreeImageBase, _ImageLikeSync):
    def popen(self, *args, **kwargs) -> ContreeProcessSync:
        # todo map parameters as needed
        return ContreeProcessSync(self.run(*args, **kwargs))

    def sync_meth(self):
        # marker for me that it's sync
        # todo delete
        ...
