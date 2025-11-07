from datetime import datetime
from enum import IntEnum

from pydantic import BaseModel


class ImageKind(IntEnum):
    INSTANCES = 0
    IMPORTED = 1


ImageTag = str


class ContreeImage(BaseModel):
    uuid: str
    tag: str
    created_at: datetime
    # kind: ImageKind
