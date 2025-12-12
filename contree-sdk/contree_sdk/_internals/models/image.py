from dataclasses import dataclass
from datetime import datetime


ImageTag = str


@dataclass
class ImageSize:
    logical: int
    physical: int


@dataclass(kw_only=True)
class ContreeImageModel:
    uuid: str
    tag: str | None = None
    created_at: datetime | None = None


@dataclass(kw_only=True)
class InspectImageResponse:
    uuid: str
    source: str | None = None
    tag: str | None = None
    created_at: int
    size: ImageSize
