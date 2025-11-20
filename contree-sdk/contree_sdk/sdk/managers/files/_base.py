from pathlib import Path

from aiofile import async_open

from contree_sdk.sdk.managers.base import BaseManager
from contree_sdk.utils.objects.file import UploadedFile


class _FilesBaseManager(BaseManager):
    async def _upload_file(self, local_path: Path | str) -> UploadedFile:
        async with async_open(local_path, "w+") as file:
            return await self._client._api.upload_file(await file.read())
