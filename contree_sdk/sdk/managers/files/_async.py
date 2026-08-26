from __future__ import annotations

from asyncio import to_thread
from pathlib import Path

from contree_sdk.sdk.managers.files._base import FilesBaseManager
from contree_sdk.utils.models.file import UploadedFile


class FilesManager(FilesBaseManager):
    async def upload_file(self, local_path: Path | str) -> UploadedFile:
        data = await to_thread(Path(local_path).read_bytes)
        result = await self.client.api.ensure_file(data)
        return UploadedFile(uuid=result.uuid, sha256=result.sha256)

    async def upload_bytes_file(self, data: bytes) -> UploadedFile:
        result = await self.client.api.ensure_file(data)
        return UploadedFile(uuid=result.uuid, sha256=result.sha256)

    async def upload(self, local_path: Path | str) -> UploadedFile:
        return await self.upload_file(local_path)
