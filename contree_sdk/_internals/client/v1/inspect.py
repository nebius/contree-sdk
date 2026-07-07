from pathlib import PurePosixPath
from uuid import UUID

from contree_sdk._internals.lib.api_decorator import get
from contree_sdk._internals.models.file import FileItemModel
from contree_sdk._internals.models.image import ContreeImageModel


class InspectMixin:
    @get("/v1/inspect/{image_uuid}/list", json=["files"])
    async def list_image_files(self, image_uuid: str | UUID, path: str | PurePosixPath) -> list[FileItemModel]: ...

    @get("/v1/inspect/{image_uuid}/download", json=False)
    async def download_image_file(self, image_uuid: str | UUID, path: str | PurePosixPath) -> bytes: ...

    @get("/v1/inspect/{image_uuid}/", json=True)
    async def get_image_by_uuid(self, image_uuid: str) -> ContreeImageModel: ...

    @get("/v1/inspect/", json=True)
    async def get_image_by_tag(self, tag: str) -> ContreeImageModel: ...
