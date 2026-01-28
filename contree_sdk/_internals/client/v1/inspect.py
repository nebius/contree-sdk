from pathlib import Path
from typing import overload
from uuid import UUID

from contree_sdk._internals.lib.api_decorator import get
from contree_sdk._internals.lib.mixins import AsyncClientMixin, SyncClientMixin
from contree_sdk._internals.models.file import FileItemModel
from contree_sdk._internals.models.image import ContreeImageModel


class InspectMixin:
    @overload
    async def list_image_files(self: AsyncClientMixin, image_uuid: str, path: str | Path) -> list[FileItemModel]: ...
    @overload
    def list_image_files(self: SyncClientMixin, image_uuid: str, path: str | Path) -> list[FileItemModel]: ...

    @get("/v1/inspect/{image_uuid}/list", json=["files"])
    def list_image_files(self, image_uuid: str, path: str | Path) -> list[FileItemModel]: ...

    @overload
    async def download_image_file(self: AsyncClientMixin, image_uuid: str | UUID, path: str | Path) -> bytes: ...
    @overload
    def download_image_file(self: SyncClientMixin, image_uuid: str | UUID, path: str | Path) -> bytes: ...

    @get("/v1/inspect/{image_uuid}/download", json=False)
    def download_image_file(self, image_uuid: str | UUID, path: str | Path) -> bytes: ...

    @overload
    async def get_image_by_uuid(self: AsyncClientMixin, image_uuid: str) -> ContreeImageModel: ...
    @overload
    def get_image_by_uuid(self: SyncClientMixin, image_uuid: str) -> ContreeImageModel: ...

    @get("/v1/inspect/{image_uuid}", json=True)
    def get_image_by_uuid(self, image_uuid: str) -> ContreeImageModel: ...

    @overload
    async def get_image_by_tag(self: AsyncClientMixin, tag: str) -> ContreeImageModel: ...
    @overload
    def get_image_by_tag(self: SyncClientMixin, tag: str) -> ContreeImageModel: ...

    @get("/v1/inspect", json=True)
    def get_image_by_tag(self, tag: str) -> ContreeImageModel: ...
