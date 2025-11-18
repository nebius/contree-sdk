from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum


class ImageKind(IntEnum):
    INSTANCES = 0
    IMPORTED = 1


ImageTag = str


@dataclass
class ImageSize:
    logical: int
    physical: int


@dataclass(kw_only=True)
class ContreeImageModel:
    uuid: str
    # source: Optional[str] = None
    tag: str | None = None
    created_at: datetime
    # size: Optional[ImageSize] = None


@dataclass(kw_only=True)
class InspectImageResponse:
    uuid: str
    source: str | None = None
    tag: str | None = None
    created_at: int
    size: ImageSize
