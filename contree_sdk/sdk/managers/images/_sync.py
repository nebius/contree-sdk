from __future__ import annotations

import logging
from contextlib import suppress
from datetime import datetime, timedelta
from urllib.parse import urlparse
from uuid import UUID

from contree_client.exceptions import NotFoundError
from contree_client.models import Image, ImageImportRegistry, ImageImportRegistryCredentials, OperationStatus

from contree_sdk.sdk.exceptions import CancelledOperationError, FailedOperationError, OperationTimedOutError
from contree_sdk.sdk.managers.images._base import ImagesBaseManager, process_time_param
from contree_sdk.sdk.objects.image import ContreeImageSync
from contree_sdk.utils.deprecation import deprecated
from contree_sdk.utils.oci import OCIReference
from contree_sdk.utils.sentinels import value_or_none
from contree_sdk.utils.typing import keep_signature


logger = logging.getLogger(__name__)


class ImagesManagerSync(ImagesBaseManager[ContreeImageSync]):
    ImageType = ContreeImageSync

    def get_images_list(
        self,
        number: int | None = 100,
        tagged: bool = False,
        since: datetime | timedelta | None = None,
        until: datetime | timedelta | None = None,
    ) -> list[ContreeImageSync]:
        """Fetch a list of images with optional filters.

        Args:
            number: Maximum number of images to return. None returns all.
            tagged: If True, return only tagged images.
            since: Return images created after this time. Accepts datetime or timedelta relative to now.
            until: Return images created before this time. Accepts datetime or timedelta relative to now.

        Returns:
            List of images matching the given filters.

        """
        return list(self.iter_images(number=number, tagged=tagged, since=since, until=until))

    def iter_images(
        self,
        number: int | None = None,
        tagged: bool = False,
        since: datetime | timedelta | None = None,
        until: datetime | timedelta | None = None,
    ):
        now = datetime.now()
        for image in self.client.api.iter_images(
            tagged=tagged,
            since=process_time_param(since, offset=timedelta(0)),
            until=process_time_param(until or now, offset=timedelta(0)),
            limit=number,
            page_size=self.client.images_list_batch_size,
        ):
            yield self.image_by_data(image)

    def use_image(self, ref: str | UUID | OCIReference, strict: bool = False) -> ContreeImageSync:
        """Resolve a reference to an image object without importing.

        Args:
            ref: Image identifier: UUID, OCI reference string, or OCIReference object.
            strict: If True, verify the image exists by fetching it from the API.

        Returns:
            Image object corresponding to the given reference.

        """
        ref = self.parse_ref(ref)
        if isinstance(ref, UUID):
            if strict:
                return self.get_image_by_uuid(ref)
            return self.ImageType(client=self.client, uuid=ref, tag=None)
        tag = ref.tag
        if strict:
            return self.get_image_by_tag(tag)
        return self.ImageType(client=self.client, uuid=None, tag=tag)

    @deprecated("Use use() or oci() instead")
    def pull_image(
        self,
        url_or_tag_or_uuid: str | UUID,
        *,
        new_tag: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> ContreeImageSync:
        uuid = url_or_tag_or_uuid if isinstance(url_or_tag_or_uuid, UUID) else None

        with suppress(ValueError):
            uuid = UUID(url_or_tag_or_uuid) if isinstance(url_or_tag_or_uuid, str) else uuid

        if uuid is not None:
            return self.get_image_by_uuid(uuid)

        if not isinstance(url_or_tag_or_uuid, str):
            raise TypeError(f"Expected str for url_or_tag_or_uuid, got {type(url_or_tag_or_uuid)}")

        parsed = urlparse(url_or_tag_or_uuid)

        if parsed.netloc or username or password:
            return self.import_image(
                url_or_tag_or_uuid,
                tag=new_tag,
                username=username,
                password=password,
                timeout=timeout,
            )

        return self.get_image_by_tag(url_or_tag_or_uuid)

    def get_image_by_tag(self, tag: str) -> ContreeImageSync:
        uuid = self.client.api.inspect_find_image_by_tag(tag)
        return self.ImageType(client=self.client, uuid=uuid, tag=tag)

    def get_image_by_uuid(self, uuid: UUID | str) -> ContreeImageSync:
        if isinstance(uuid, str):
            uuid = UUID(uuid)
        return self.image_by_data(self.client.api.inspect_image(str(uuid)))

    def import_image(
        self,
        image: str | OCIReference,
        *,
        tag: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> ContreeImageSync:
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
            CancelledOperationError: If the import operation was cancelled.
            OperationTimedOutError: If the import operation did not complete within `timeout`.

        """
        ref = self.parse_ref(image)
        if isinstance(ref, UUID):
            raise ValueError(f"Cannot import image by UUID {ref}")  # noqa: TRY004

        new_tag = tag or ref.tag
        image_url = ref.url

        if username or password:
            if not (username and password):
                raise ValueError("Both username and password must be provided")
            registry = ImageImportRegistry(
                url=image_url,
                credentials=ImageImportRegistryCredentials(username=username, password=password),
            )
        else:
            registry = ImageImportRegistry(url=image_url)

        timeout = timeout or self.client.operation_import_timeout or self.client.operation_timeout

        operation_id = self.client.api.import_image(registry, tag=new_tag, timeout=round(timeout))
        try:
            response = self.client.api.wait_operation(operation_id, timeout=timeout)
        except TimeoutError as e:
            raise OperationTimedOutError(operation_uuid=UUID(operation_id)) from e

        if response.status == OperationStatus.CANCELLED:
            raise CancelledOperationError(operation_uuid=UUID(operation_id))
        if response.status == OperationStatus.FAILED:
            error = value_or_none(response.error) or "Unknown error"
            raise FailedOperationError(operation_uuid=UUID(operation_id), error=error)

        result_image_uuid = value_or_none(response.result_image_uuid)
        if result_image_uuid is None:
            raise FailedOperationError(
                operation_uuid=UUID(operation_id),
                error="Image import returned no image uuid",
            )
        return self.image_by_data(Image(uuid=result_image_uuid, tag=new_tag))

    def pull_image_by_oci(
        self,
        ref: str | OCIReference | UUID,
        *,
        tag: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> ContreeImageSync:
        """Resolve an image by tag, falling back to import if not found.

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
        ref = self.parse_ref(ref)
        if tag and isinstance(ref, OCIReference):
            ref = OCIReference(url=ref.url, tag=tag)
        try:
            logger.debug(f"Attempting to use existing image: {ref}")
            return self.use_image(ref, strict=True)
        except NotFoundError:
            if isinstance(ref, UUID):
                raise
            logger.debug(f"Falling back to import: {ref}")
            return self.import_image(ref, tag=tag, username=username, password=password, timeout=timeout)

    @keep_signature(get_images_list)
    def __call__(self, *args, **kwargs) -> list[ContreeImageSync]:
        return self.get_images_list(*args, **kwargs)

    def __iter__(self):
        yield from self.iter_images()

    @keep_signature(use_image)
    def use(self, *args, **kwargs) -> ContreeImageSync:
        return self.use_image(*args, **kwargs)

    def pull(
        self,
        url_or_tag_or_uuid: str | UUID,
        *,
        new_tag: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ) -> ContreeImageSync:
        return self.pull_image(
            url_or_tag_or_uuid, new_tag=new_tag, username=username, password=password, timeout=timeout
        )

    @keep_signature(pull_image_by_oci)
    def oci(self, *args, **kwargs) -> ContreeImageSync:
        return self.pull_image_by_oci(*args, **kwargs)

    docker = podman = pull_by_oci = oci

    @keep_signature(import_image)
    def import_from(self, *args, **kwargs) -> ContreeImageSync:
        return self.import_image(*args, **kwargs)
