from __future__ import annotations

from pathlib import Path

from contree_sdk.sdk.managers.files._base import FilesBaseManager
from contree_sdk.utils.models.file import UploadedFile


class FilesManagerSync(FilesBaseManager):
    def upload_file(self, local_path: Path | str) -> UploadedFile:
        data = Path(local_path).read_bytes()
        result = self.client.api.ensure_file(data)
        return UploadedFile(uuid=result.uuid, sha256=result.sha256)

    def upload_bytes_file(self, data: bytes) -> UploadedFile:
        result = self.client.api.ensure_file(data)
        return UploadedFile(uuid=result.uuid, sha256=result.sha256)

    def upload(self, local_path: Path | str) -> UploadedFile:
        return self.upload_file(local_path)
