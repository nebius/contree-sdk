from typing import Annotated, overload

from contree_sdk.api.lib.decorator import get, post
from contree_sdk.api.lib.mixins import AsyncClientMixin, SyncClientMixin
from contree_sdk.api.lib.types import Body
from contree_sdk.api.models.image import ContreeImageModel, ImageKind
from contree_sdk.api.models.image_import import ImageImportRequest


class ImagesMixin:
    @overload
    async def get_images(self: AsyncClientMixin, kind: ImageKind | None = None) -> list[ContreeImageModel]: ...
    @overload
    def get_images(self: SyncClientMixin, kind: ImageKind | None = None) -> list[ContreeImageModel]: ...

    @get("/v1/images", json=["images"])
    def get_images(self, kind: ImageKind | None = None) -> list[ContreeImageModel]: ...

    @overload
    async def start_import_image(self: AsyncClientMixin, request: Annotated[ImageImportRequest, Body]) -> str: ...
    @overload
    def start_import_image(self: SyncClientMixin, request: Annotated[ImageImportRequest, Body]) -> str: ...
    @post("/v1/images/import", json=["uuid"])
    def start_import_image(self, request: Annotated[ImageImportRequest, Body]) -> str: ...


# todo later use like this MainV1Client(ImagesMixin['/images'], OtherMixin, ContreeClientBase) and have all in one
