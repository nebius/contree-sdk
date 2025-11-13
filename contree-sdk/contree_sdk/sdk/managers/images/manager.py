from contree_sdk.sdk.managers.images.base import _ImagesBaseManager


class ImagesManager(_ImagesBaseManager):
    __call__ = _ImagesBaseManager._get_images

    pull = _ImagesBaseManager._pull_image
