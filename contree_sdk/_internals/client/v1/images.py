from typing import Annotated, Literal

from contree_sdk._internals.lib.api_decorator import delete, get, patch, post
from contree_sdk._internals.lib.types import Body
from contree_sdk._internals.models.image import ContreeImageModel
from contree_sdk._internals.models.image_import import ImageImportRequest
from contree_sdk.utils.models.image import ImageKind


class ImagesMixin:
    @get("/v1/images", json=["images"])
    async def get_images(
        self,
        kind: ImageKind | None = None,
        limit: int | None = None,
        offset: int | None = None,
        tagged: Literal[0, 1] | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[ContreeImageModel]: ...

    @post("/v1/images/import", json=["uuid"])
    async def start_import_image(self, request: Annotated[ImageImportRequest, Body]) -> str: ...

    @patch("/v1/images/{image_uuid}/tag", json=True)
    async def tag_image(self, image_uuid: str, tag: Annotated[str, Body]) -> ContreeImageModel: ...

    @delete("/v1/images/{image_uuid}/tag", json=True)
    async def untag_image(self, image_uuid: str) -> ContreeImageModel: ...


# todo later use like this MainV1Client(ImagesMixin['/images'], OtherMixin, ClientBase) and have all in one
