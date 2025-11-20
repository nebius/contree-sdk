from pathlib import Path

from contree_sdk.sdk.managers.files._base import _FilesBaseManager
from contree_sdk.utils.objects.file import UploadedFile
from contree_sdk.utils.wrapper import coro_sync


class FilesManagerSync(_FilesBaseManager):
    def upload(self, local_path: Path | str) -> UploadedFile:
        return coro_sync(self._upload_file(local_path))
