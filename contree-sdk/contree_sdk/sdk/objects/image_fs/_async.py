from dataclasses import dataclass
from pathlib import Path

from contree_sdk.sdk.objects.file._base import _ImageFileBase


@dataclass(frozen=True, kw_only=True)
class ImageFile(_ImageFileBase):
    async def download(self, local_path: str | Path):
        await self._download(local_path)
