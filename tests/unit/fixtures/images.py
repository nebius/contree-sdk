from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from contree_client.models import Image, ImageListResponse

from contree_sdk import Contree, ContreeSync
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync


@pytest.fixture
def image_uuid() -> UUID:
    return uuid4()


@pytest.fixture
def image_tag() -> str:
    return "busybox:latest"


def queue_image_lookup(api: Any, image_uuid: UUID, image_tag: str) -> None:
    image = Image(uuid=str(image_uuid), tag=image_tag, created_at="2024-01-01T12:00:00+00:00")
    api.mock("list_images", ImageListResponse(images=[image]))
    api.mock("inspect_image", image)
    api.mock("inspect_find_image_by_tag", str(image_uuid))


def queue_tag(api: Any, image_uuid: UUID, tag: str | None, *, count: int = 1) -> None:
    for _ in range(count):
        api.mock("update_image_tag", Image(uuid=str(image_uuid), tag=tag))


def queue_untag(api: Any, *, count: int = 1) -> None:
    for _ in range(count):
        api.mock("delete_image_tag", None)


@pytest.fixture
def fake_image(fake_contree: Contree, image_uuid: UUID, image_tag: str) -> ContreeImage:
    queue_image_lookup(fake_contree.api, image_uuid, image_tag)
    return ContreeImage(client=fake_contree, uuid=image_uuid, tag=image_tag)


@pytest.fixture
def fake_image_s(fake_contree_s: ContreeSync, image_uuid: UUID, image_tag: str) -> ContreeImageSync:
    queue_image_lookup(fake_contree_s.api, image_uuid, image_tag)
    return ContreeImageSync(client=fake_contree_s, uuid=image_uuid, tag=image_tag)
