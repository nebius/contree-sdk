from typing import Annotated, overload

from contree_sdk._internals.lib.decorator import get, head, post
from contree_sdk._internals.lib.mixins import AsyncClientMixin, SyncClientMixin
from contree_sdk._internals.lib.types import FileContent, OctetFile
from contree_sdk.utils.objects.file import UploadedFile


class FilesMixin:
    @overload
    async def get_file_by_sha256(self: AsyncClientMixin, sha256: str) -> UploadedFile: ...
    @overload
    def get_file_by_sha256(self: SyncClientMixin, sha256: str) -> UploadedFile: ...

    @get("/v1/files", json=True)
    def get_file_by_sha256(self, sha256: str) -> UploadedFile: ...

    @overload
    async def check_file_exists(self: AsyncClientMixin, uuid: str) -> bool: ...
    @overload
    def check_file_exists(self: SyncClientMixin, uuid: str) -> bool: ...

    @head("/v1/files")
    def check_file_exists(self, uuid: str) -> bool: ...

    @overload
    async def upload_file(self: AsyncClientMixin, data: Annotated[FileContent, OctetFile]) -> UploadedFile: ...
    @overload
    def upload_file(self: SyncClientMixin, data: Annotated[FileContent, OctetFile]) -> UploadedFile: ...

    @post("/v1/files", json=True)
    def upload_file(self, data: Annotated[FileContent, OctetFile]) -> UploadedFile: ...

    # todo add error templates to response
