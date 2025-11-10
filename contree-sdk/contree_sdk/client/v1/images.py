from typing import Annotated, overload

from contree_sdk.client.decorator import get, post
from contree_sdk.client.mixins import AsyncClientMixin, SyncClientMixin
from contree_sdk.client.types import Body
from contree_sdk.models.image import ContreeImage, ImageKind
from contree_sdk.models.image_import import ImageImportOperation, ImageImportRequest


class ImagesMixin:
    @overload
    async def get_images(self: AsyncClientMixin, kind: ImageKind | None = None) -> list[ContreeImage]: ...
    @overload
    def get_images(self: SyncClientMixin, kind: ImageKind | None = None) -> list[ContreeImage]: ...

    @get("/v1/images", json=["images"])
    def get_images(self, kind: ImageKind | None = None) -> list[ContreeImage]: ...

    @overload
    async def get_image_import_status(self: AsyncClientMixin, operation_id: str) -> ImageImportOperation: ...
    @overload
    def get_image_import_status(self: SyncClientMixin, operation_id: str) -> ImageImportOperation: ...

    @get("/v1/images/{operation_id}", json=True)
    def get_image_import_status(self, operation_id: str) -> ImageImportOperation: ...

    @overload
    async def import_image(self: AsyncClientMixin, request: Annotated[ImageImportRequest, Body]) -> str: ...
    @overload
    def import_image(self: SyncClientMixin, request: Annotated[ImageImportRequest, Body]) -> str: ...

    @post("/v1/images/import", json=["uuid"])
    def import_image(self, request: Annotated[ImageImportRequest, Body]) -> str: ...


# todo later use like this MainV1Client(ImagesMixin['/images'], OtherMixin, ContreeClientBase) and have all in one
