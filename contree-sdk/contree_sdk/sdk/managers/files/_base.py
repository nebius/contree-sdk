from contextlib import suppress
from hashlib import sha256
from pathlib import Path

import aiofiles

from contree_sdk._internals.utils.exception import wrap_api_call
from contree_sdk.sdk.exceptions import NotFoundError
from contree_sdk.sdk.managers._base import BaseManager
from contree_sdk.utils.models.file import UploadedFile


def _sha256(data: bytes) -> str:
    return sha256(data).hexdigest()


class _FilesBaseManager(BaseManager):
    async def _upload_file(self, local_path: Path | str) -> UploadedFile:
        async with aiofiles.open(local_path, "rb") as file:
            file_hash = sha256()
            while chunk := await file.read(self._client.config.file_upload_chunk_size):
                file_hash.update(chunk)

            with suppress(NotFoundError), wrap_api_call():
                return await self._client._api.get_file_by_sha256(file_hash.hexdigest())

        async with aiofiles.open(local_path, "rb") as file:
            with wrap_api_call():
                return await self._client._api.upload_file(file)
