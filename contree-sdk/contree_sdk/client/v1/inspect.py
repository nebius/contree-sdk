from typing import overload

from contree_sdk.lib.decorator import get
from contree_sdk.lib.mixins import AsyncClientMixin, SyncClientMixin
from contree_sdk.models.file import DirectoryList
from contree_sdk.models.image import ContreeImage, InspectImageResponse


class InspectMixin:
    @overload
    async def inspect_image(self: AsyncClientMixin, image_uuid: str) -> InspectImageResponse: ...
    @overload
    def inspect_image(self: SyncClientMixin, image_uuid: str) -> InspectImageResponse: ...

    # todo try to reuse ContreeImage

    @get("/v1/inspect/{image_uuid}/", json=True)
    def inspect_image(self, image_uuid: str) -> ContreeImage: ...

    @overload
    async def list_image_files(self: AsyncClientMixin, image_uuid: str, path: str) -> DirectoryList: ...
    @overload
    def list_image_files(self: SyncClientMixin, image_uuid: str, path: str) -> DirectoryList: ...

    @get("/v1/inspect/{image_uuid}/list", json=True)
    def list_image_files(self, image_uuid: str, path: str) -> DirectoryList: ...

    # @overload
    # async def download_image_file(self: AsyncClientMixin, image_uuid: str, path: str) -> bytes: ...
    # @overload
    # def download_image_file(self: SyncClientMixin, image_uuid: str, path: str) -> bytes: ...
    #
    # @get("/v1/inspect/{image_uuid}/download", json=False)
    # def download_image_file(self, image_uuid: str, path: str) -> bytes: ...
