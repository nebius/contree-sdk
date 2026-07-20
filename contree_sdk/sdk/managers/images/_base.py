import logging
from collections.abc import AsyncGenerator
from contextlib import suppress
from datetime import datetime, timedelta
from typing import Generic, TypeVar
from urllib.parse import urlparse
from uuid import UUID

from contree_sdk._internals.models.image import ContreeImageModel
from contree_sdk._internals.models.image_import import (
    ImageImportRequest,
    PrivateRegistryInfo,
    PublicRegistryInfo,
    RegistryCredentials,
)
from contree_sdk.sdk.exceptions import FailedOperationError, NotFoundError
from contree_sdk.sdk.managers._base import BaseManager
from contree_sdk.sdk.objects.image._base import _ContreeImageBase
from contree_sdk.utils.models.image import ImageKind
from contree_sdk.utils.oci import OCIReference


_ImageT = TypeVar("_ImageT", bound=_ContreeImageBase)

logger = logging.getLogger(__name__)


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
        """Fetch a list of images with optional filters.

        Args:
            number: Maximum number of images to return. None returns all.
            kind: Filter by image kind.
            tagged: If True, return only tagged images.
            since: Return images created after this time. Accepts datetime or timedelta relative to now.
            until: Return images created before this time. Accepts datetime or timedelta relative to now.

        Returns:
            List of images matching the given filters.

        """
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
        """Resolve a reference to an image object without importing.

        Args:
            ref: Image identifier — UUID, OCI reference string, or OCIReference object.
            strict: If True, verify the image exists by fetching it from the API.

        Returns:
            Image object corresponding to the given reference.

        """
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
        """Outdated method for pulling images. Use ``use()`` or ``oci()`` instead.

        .. deprecated::
            Use :meth:`use` to reference an image by tag or UUID,
            or :meth:`oci` / :meth:`import_from` to import from an external source.

        Args:
            url_or_tag_or_uuid: UUID, local tag, or external registry URL of the image.
            new_tag: Tag to assign to the imported image.
            username: Registry username for authenticated imports.
            password: Registry password for authenticated imports.
            timeout: Maximum seconds to wait for the import operation.

        Returns:
            Resolved or imported image object.

        Raises:
            TypeError: If url_or_tag_or_uuid is not a str or UUID.

        """
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
                tag=new_tag,
                username=username,
                password=password,
                timeout=timeout,
            )

        # return by tag
        return await self._get_image_by_tag(url_or_tag_or_uuid)

    async def _get_image_by_tag(self, tag: str) -> _ImageT:
        resp = await self._client._api.get_image_by_tag(tag)
        if resp.tag is None:
            resp.tag = tag
        return self._image_by_data(resp)

    async def _get_image_by_uuid(self, uuid: UUID | str) -> _ImageT:
        if isinstance(uuid, str):
            uuid = UUID(uuid)

        return self._image_by_data(await self._client._api.get_image_by_uuid(str(uuid)))

    async def _import_image(
        self,
        image: str | OCIReference,
        *,
        tag: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> _ImageT:
        """Import an image from an external registry into Contree.

        Args:
            image: OCI reference string or OCIReference pointing to the source image.
            tag: Tag to assign to the imported image. Defaults to the tag in the reference.
            username: Registry username for private registries.
            password: Registry password for private registries.
            timeout: Maximum seconds to wait for the import operation.

        Returns:
            Imported image object.

        Raises:
            ValueError: If image is a UUID or credentials are incomplete.
            FailedOperationError: If the import operation completes without returning an image.

        """
        ref = self._parse_ref(image)
        if isinstance(ref, UUID):
            raise ValueError(f"Cannot import image by UUID {ref}")  # noqa: TRY004

        new_tag = tag or ref.tag
        image_url = ref.url

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

        self._client._warn_if_timeout_exceeds_limit(timeout, "images_import_max_timeout")

        operation_uuid = await self._client._start_operation(
            ImageImportRequest(
                registry=registry,
                tag=new_tag,
                timeout=round(timeout),
            )
        )
        operation_result, _ = await self._client._wait_operation(
            operation_uuid=operation_uuid,
            timeout=timeout,
            spid=None,
        )
        if operation_result.result_image_uuid is None:
            raise FailedOperationError(
                operation_uuid=operation_uuid,
                error="Image import returned no image uuid",
            )
        return self._image_by_data(
            ContreeImageModel(
                uuid=operation_result.result_image_uuid,
                tag=ref.tag,
            )
        )

    async def _pull_image_by_oci(
        self,
        ref: str | OCIReference | UUID,
        *,
        tag: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> _ImageT:
        """Resolve an image by tag, falling back to import if not found.

        Derives the target tag from the ``tag`` parameter or from the reference itself,
        then tries to find an existing image with that tag. If the image does not exist,
        triggers an import and returns the result.

        Args:
            ref: UUID, OCI reference string, or OCIReference of the image.
            tag: Tag override; if provided, replaces the tag from the reference.
            username: Registry username for authenticated imports.
            password: Registry password for authenticated imports.
            timeout: Maximum seconds to wait for the import operation.

        Returns:
            Resolved or imported image object.

        Raises:
            NotFoundError: If ref is a UUID and the image does not exist.

        """
        ref = self._parse_ref(ref)
        if tag and isinstance(ref, OCIReference):
            ref = OCIReference(
                url=ref.url,
                tag=tag,
            )
        try:
            logger.debug(f"Attempting to use existing image: {ref}")
            return await self._use_image(ref, strict=True)
        except NotFoundError:
            if isinstance(ref, UUID):
                raise
            logger.debug(f"Falling back to import: {ref}")
            return await self._import_image(ref, tag=tag, username=username, password=password, timeout=timeout)
