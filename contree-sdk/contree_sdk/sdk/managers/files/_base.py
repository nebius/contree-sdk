from asyncio import to_thread
from contextlib import suppress
from hashlib import sha256
from pathlib import Path

from contree_sdk._internals.utils.exception import wrap_api_call
from contree_sdk.sdk.exceptions import NotFoundError
from contree_sdk.sdk.managers._base import BaseManager
from contree_sdk.utils.models.file import UploadedFile


def _sha256(data: bytes) -> str:
    return sha256(data).hexdigest()


class _FilesBaseManager(BaseManager):
    async def _upload_file(self, local_path: Path | str) -> UploadedFile:
        with await to_thread(open, local_path, "rb") as file:
            data = await to_thread(file.read)
            file_hash = await to_thread(_sha256, data)
            with suppress(NotFoundError), wrap_api_call():
                return await self._client._api.get_file_by_sha256(file_hash)

            with wrap_api_call():
                return await self._client._api.upload_file(data)
