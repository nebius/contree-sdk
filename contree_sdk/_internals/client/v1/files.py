from typing import Annotated

from contree_sdk._internals.lib.api_decorator import get, head, post
from contree_sdk._internals.lib.types import FileContent, OctetFile
from contree_sdk.utils.models.file import UploadedFile


class FilesMixin:
    @get("/v1/files/{sha256}", json=True)
    async def get_file_by_sha256(self, sha256: str) -> UploadedFile: ...

    @head("/v1/files/{sha256}")
    async def check_file_exists(self, sha256: str) -> bool: ...

    @post("/v1/files", json=True)
    async def upload_file(self, data: Annotated[FileContent, OctetFile]) -> UploadedFile: ...

    # todo add error templates to response
