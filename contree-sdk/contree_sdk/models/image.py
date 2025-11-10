from datetime import datetime
from enum import IntEnum

from pydantic import BaseModel


class ImageKind(IntEnum):
    INSTANCES = 0
    IMPORTED = 1


ImageTag = str


class ImageSize(BaseModel):
    logical: int
    physical: int


class ContreeImage(BaseModel):
    uuid: str
    # source: Optional[str] = None
    tag: str | None = None
    created_at: datetime
    # size: Optional[ImageSize] = None


class InspectImageResponse(BaseModel):
    uuid: str
    source: str | None = None
    tag: str | None = None
    created_at: int
    size: ImageSize
