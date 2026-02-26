from collections.abc import AsyncGenerator
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Generic, TypeVar
from urllib.parse import ParseResult, urlparse
from uuid import UUID

from contree_sdk._internals.models.image import ContreeImageModel
from contree_sdk._internals.models.image_import import (
    ImageImportRequest,
    PrivateRegistryInfo,
    PublicRegistryInfo,
    RegistryCredentials,
)
from contree_sdk._internals.utils.exception import wrap_api_call
from contree_sdk.sdk.exceptions import FailedOperationError
from contree_sdk.sdk.managers._base import BaseManager
from contree_sdk.sdk.objects.image._base import _ContreeImageBase
from contree_sdk.utils.models.image import ImageKind
from contree_sdk.utils.oci import OCIReference


_ImageT = TypeVar("_ImageT", bound=_ContreeImageBase)


def _process_time_param(value: datetime | timedelta | None, offset: timedelta) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    value += offset
    seconds = value.total_seconds()
    return f"{seconds:.0f}s"


class _ImagesBaseManager(BaseManager, Generic[_ImageT]):
    _ImageType: type[_ImageT]

    async def _get_images(
        self,
        number: int | None = 100,
        kind: ImageKind | None = None,
        tagged: bool = False,
        since: datetime | timedelta | None = None,
        until: datetime | timedelta | None = None,
    ) -> list[_ImageT]:
        return [
            image
            async for image in self._iter(
                number=number,
                kind=kind,
                tagged=tagged,
                since=since,
                until=until,
            )
        ]

    async def _iter(
        self,
        number: int | None = None,
        kind: ImageKind | None = None,
        tagged: bool = False,
        since: datetime | timedelta | None = None,
        until: datetime | timedelta | None = None,
    ) -> AsyncGenerator[_ImageT, None]:
        started = datetime.now()

        until = until or started
        current_offset = 0
        batch_size = self._client.config.images_list_batch_size

        while True:
            timedelta_offset = datetime.now() - started
            limit = batch_size
            if number is not None:
                limit = min(limit, number - current_offset)

            with wrap_api_call():
                batch = await self._client._api.get_images(
                    offset=current_offset,
                    limit=limit,
                    since=_process_time_param(since, offset=timedelta_offset),
                    until=_process_time_param(until, offset=timedelta_offset),
                    tagged=1 if tagged else None,
                    kind=kind or None,
                )
            for image in batch:
                yield self._image_by_data(image)

            current_offset += len(batch)

            if len(batch) < batch_size:
                break  # no more images
            if number is not None and current_offset >= number:
                break  # returned all requested images

    @classmethod
    def _parse_ref(cls, ref: str | UUID | OCIReference) -> UUID | OCIReference:
        if isinstance(ref, OCIReference):
            return ref

        if isinstance(ref, UUID):
            return ref

        with suppress(ValueError):
            return UUID(ref)

        return OCIReference.from_oci(ref)

    async def _use_image(self, ref: str | UUID | OCIReference, strict: bool = False) -> _ImageT:
        ref = self._parse_ref(ref)
        if isinstance(ref, UUID):
            if strict:
                return await self._get_image_by_uuid(ref)
            return self._ImageType(client=self._client, uuid=ref, tag=None)
        tag = ref.tag
        if strict:
            return await self._get_image_by_tag(tag)
        return self._ImageType(client=self._client, uuid=None, tag=tag)

    def _image_by_data(self, image: ContreeImageModel) -> _ImageT:
        return self._ImageType(
            client=self._client,
            uuid=image.uuid,
            tag=image.tag,
        )

    async def _pull_image(
        self,
        url_or_tag_or_uuid: str | UUID,
        *,
        new_tag: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> _ImageT:
        uuid = url_or_tag_or_uuid if isinstance(url_or_tag_or_uuid, UUID) else None

        with suppress(ValueError):
            uuid = UUID(url_or_tag_or_uuid) if isinstance(url_or_tag_or_uuid, str) else uuid

        if uuid is not None:
            return await self._get_image_by_uuid(uuid)

        if not isinstance(url_or_tag_or_uuid, str):
            raise TypeError(f"Expected str for url_or_tag_or_uuid, got {type(url_or_tag_or_uuid)}")

        parsed = urlparse(url_or_tag_or_uuid)

        if parsed.netloc or username or password:
            return await self._import_image(
                url_or_tag_or_uuid,
                new_tag=new_tag,
                username=username,
                password=password,
                timeout=timeout,
            )

        # return by tag
        return await self._get_image_by_tag(url_or_tag_or_uuid)

    async def _get_image_by_tag(self, tag: str) -> _ImageT:
        with wrap_api_call():
            return self._image_by_data(await self._client._api.get_image_by_tag(tag))

    async def _get_image_by_uuid(self, uuid: UUID | str) -> _ImageT:
        if isinstance(uuid, str):
            uuid = UUID(uuid)

        with wrap_api_call():
            return self._image_by_data(await self._client._api.get_image_by_uuid(str(uuid)))

    async def _import_image(
        self,
        image_url: str | ParseResult,
        *,
        new_tag: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> _ImageT:
        if isinstance(image_url, str):
            image_url = urlparse(image_url)

        new_tag = new_tag or image_url.path.removeprefix("/")
        image_url = image_url.geturl()

        if username or password:
            if not (username and password):
                raise ValueError("Both username and password must be provided")
            registry = PrivateRegistryInfo(
                url=image_url,
                credentials=RegistryCredentials(username=username, password=password),
            )
        else:
            registry = PublicRegistryInfo(url=image_url)

        timeout = timeout or self._client.config.operation_import_timeout or self._client.config.operation_timeout
        with wrap_api_call():
            operation_uuid = await self._client._api.start_import_image(
                ImageImportRequest(
                    registry=registry,
                    tag=new_tag,
                    timeout=round(timeout),
                )
            )
        _, image_info = await self._client._wait_operation(
            operation_uuid=operation_uuid,
            result_type=ImageImportRequest,
            timeout=timeout,
        )
        if image_info.image is None:
            raise FailedOperationError(
                operation_uuid=operation_uuid if isinstance(operation_uuid, UUID) else UUID(operation_uuid),
                error="Image import returned no image uuid",
            )
        return self._image_by_data(
            ContreeImageModel(
                uuid=image_info.image,
                tag=image_info.tag,
            )
        )
