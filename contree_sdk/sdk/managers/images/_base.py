from __future__ import annotations

from contextlib import suppress
from datetime import datetime, timedelta
from typing import Generic, TypeVar
from uuid import UUID

from contree_client.models import Image

from contree_sdk.sdk.managers._base import BaseManager
from contree_sdk.sdk.objects.image._base import ContreeImageBase
from contree_sdk.utils.oci import OCIReference
from contree_sdk.utils.sentinels import value_or_none


ImageT = TypeVar("ImageT", bound=ContreeImageBase)


def process_time_param(value: datetime | timedelta | None, offset: timedelta) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    value += offset
    seconds = value.total_seconds()
    return f"{seconds:.0f}s"


class ImagesBaseManager(BaseManager, Generic[ImageT]):
    ImageType: type[ImageT]

    @classmethod
    def parse_ref(cls, ref: str | UUID | OCIReference) -> UUID | OCIReference:
        if isinstance(ref, OCIReference):
            return ref

        if isinstance(ref, UUID):
            return ref

        with suppress(ValueError):
            return UUID(ref)

        return OCIReference.from_oci(ref)

    def image_by_data(self, image: Image) -> ImageT:
        return self.ImageType(client=self.client, uuid=value_or_none(image.uuid), tag=value_or_none(image.tag))
