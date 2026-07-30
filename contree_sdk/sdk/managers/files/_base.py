from asyncio import to_thread
from contextlib import suppress
from hashlib import sha256
from pathlib import Path

import aiofiles
from contree_client.models import File, FileResponse

from contree_sdk.sdk.exceptions import NotFoundError
from contree_sdk.sdk.managers._base import BaseManager
from contree_sdk.utils.models.file import UploadedFile


def _as_uploaded_file(file: File | FileResponse) -> UploadedFile:
    return UploadedFile(uuid=file.uuid, sha256=file.sha256)


class _FilesBaseManager(BaseManager):
    async def _upload_file(self, local_path: Path | str) -> UploadedFile:
        async with aiofiles.open(local_path, "rb") as file:
            file_hash = sha256()
            while chunk := await file.read(self._client.config.file_upload_chunk_size):
                file_hash.update(chunk)

            with suppress(NotFoundError):
                return _as_uploaded_file(await self._client._api.get_file(file_hash.hexdigest()))

        file = await to_thread(open, local_path, "rb")
        try:
            return _as_uploaded_file(await self._client._api.upload_file(file))
        finally:
            await to_thread(file.close)

    async def _upload_bytes_file(self, data: bytes) -> UploadedFile:
        file_hash = sha256()
        file_hash.update(data)

        with suppress(NotFoundError):
            return _as_uploaded_file(await self._client._api.get_file(file_hash.hexdigest()))
        return _as_uploaded_file(await self._client._api.upload_file(data))
