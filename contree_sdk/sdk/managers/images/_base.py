from __future__ import annotations

from contextlib import suppress
from typing import Generic, TypeVar
from uuid import UUID

from contree_client.models import Image

from contree_sdk.sdk.managers._base import BaseManager
from contree_sdk.sdk.objects.image._base import ContreeImageBase
from contree_sdk.utils.oci import OCIReference
from contree_sdk.utils.sentinels import value_or_none


ImageT = TypeVar("ImageT", bound=ContreeImageBase)


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
