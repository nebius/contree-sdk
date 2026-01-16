from typing import Annotated, overload

from contree_sdk._internals.lib.api_decorator import get, post
from contree_sdk._internals.lib.mixins import AsyncClientMixin, SyncClientMixin
from contree_sdk._internals.lib.types import Body
from contree_sdk._internals.models.image import ContreeImageModel
from contree_sdk._internals.models.image_import import ImageImportRequest
from contree_sdk.utils.models.image import ImageKind


class ImagesMixin:
    @overload
    async def get_images(
        self: AsyncClientMixin,
        kind: ImageKind | None = None,
        limit: int | None = None,
        offset: int | None = None,
        tagged: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[ContreeImageModel]: ...
    @overload
    def get_images(
        self: SyncClientMixin,
        kind: ImageKind | None = None,
        limit: int | None = None,
        offset: int | None = None,
        tagged: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[ContreeImageModel]: ...

    @get("/v1/images", json=["images"])
    def get_images(
        self,
        kind: ImageKind | None = None,
        limit: int | None = None,
        offset: int | None = None,
        tagged: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[ContreeImageModel]: ...

    @overload
    async def start_import_image(self: AsyncClientMixin, request: Annotated[ImageImportRequest, Body]) -> str: ...
    @overload
    def start_import_image(self: SyncClientMixin, request: Annotated[ImageImportRequest, Body]) -> str: ...
    @post("/v1/images/import", json=["uuid"])
    def start_import_image(self, request: Annotated[ImageImportRequest, Body]) -> str: ...


# todo later use like this MainV1Client(ImagesMixin['/images'], OtherMixin, ContreeClientBase) and have all in one
