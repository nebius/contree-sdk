from dataclasses import dataclass
from pathlib import Path

from contree_sdk.sdk.objects.file._base import _ImageFileBase
from contree_sdk.utils.wrapper import coro_sync


@dataclass(frozen=True, kw_only=True)
class ImageFileSync(_ImageFileBase):
    def download(self, local_path: str | Path):
        coro_sync(self._download(local_path))
