from contree_client.exceptions import NotFoundError
from contree_client.models import Image, ImageListResponse
from contree_client.testing import ContreeAsyncClient, ContreeClient
from examples.images.list_images import main as list_images_main
from examples.images.list_images_sync import main as list_images_main_s
from examples.images.pull_image import main as pull_image_main
from examples.images.pull_image_sync import main as pull_image_main_s
from examples.images.tag_image import main as tag_image_main
from examples.images.tag_image_sync import main as tag_image_main_s
from examples.images.tag_on_run import main as tag_on_run_main
from examples.images.tag_on_run_sync import main as tag_on_run_main_s
from examples.images.use_by_tag import main as use_by_tag_main
from examples.images.use_by_tag_sync import main as use_by_tag_main_s

from tests.unit.fixtures.images import queue_image_lookup, queue_tag, queue_untag
from tests.unit.fixtures.imports import queue_import
from tests.unit.fixtures.operations import queue_run


async def test_list_images_example(fake_api: ContreeAsyncClient, image_uuid, image_tag):
    fake_api.mock("list_images", ImageListResponse(images=[Image(uuid=str(image_uuid), tag=image_tag)]))
    await list_images_main(fake_api)


def test_list_images_example_s(fake_api_s: ContreeClient, image_uuid, image_tag):
    fake_api_s.mock("list_images", ImageListResponse(images=[Image(uuid=str(image_uuid), tag=image_tag)]))
    list_images_main_s(fake_api_s)


async def test_pull_image_example(fake_api: ContreeAsyncClient, image_uuid, image_tag, result_image_uuid):
    fake_api.mock("list_images", ImageListResponse(images=[Image(uuid=str(image_uuid), tag=image_tag)]))
    fake_api.mock("inspect_image", Image(uuid=str(image_uuid), tag=image_tag))
    # First lookup (by the listed tag) succeeds; the `.oci()` call's internal
    # strict lookup (for the registry ref's own tag) then misses, triggering
    # the import fallback.
    fake_api.mock("inspect_find_image_by_tag", str(image_uuid))
    fake_api.mock("inspect_find_image_by_tag", error=NotFoundError(404, "image not found"))
    queue_import(fake_api, result_image_uuid=result_image_uuid)

    await pull_image_main(fake_api)


def test_pull_image_example_s(fake_api_s: ContreeClient, image_uuid, image_tag, result_image_uuid):
    fake_api_s.mock("list_images", ImageListResponse(images=[Image(uuid=str(image_uuid), tag=image_tag)]))
    fake_api_s.mock("inspect_image", Image(uuid=str(image_uuid), tag=image_tag))
    fake_api_s.mock("inspect_find_image_by_tag", str(image_uuid))
    fake_api_s.mock("inspect_find_image_by_tag", error=NotFoundError(404, "image not found"))
    queue_import(fake_api_s, result_image_uuid=result_image_uuid)

    pull_image_main_s(fake_api_s)


async def test_tag_image_example(fake_api: ContreeAsyncClient, image_uuid, image_tag, result_image_uuid):
    queue_image_lookup(fake_api, image_uuid, image_tag)
    queue_tag(fake_api, image_uuid, "my-custom-tag:v1")
    queue_untag(fake_api)
    queue_run(fake_api, result_image_uuid=str(result_image_uuid))

    await tag_image_main(fake_api)


def test_tag_image_example_s(fake_api_s: ContreeClient, image_uuid, image_tag, result_image_uuid):
    queue_image_lookup(fake_api_s, image_uuid, image_tag)
    queue_tag(fake_api_s, image_uuid, "my-custom-tag:v1")
    queue_untag(fake_api_s)
    queue_run(fake_api_s, result_image_uuid=str(result_image_uuid))

    tag_image_main_s(fake_api_s)


async def test_use_by_tag_example(fake_api: ContreeAsyncClient, result_image_uuid):
    queue_run(fake_api, stdout="hello\n", result_image_uuid=str(result_image_uuid))
    await use_by_tag_main(fake_api)


def test_use_by_tag_example_s(fake_api_s: ContreeClient, result_image_uuid):
    queue_run(fake_api_s, stdout="hello\n", result_image_uuid=str(result_image_uuid))
    use_by_tag_main_s(fake_api_s)


async def test_tag_on_run_example(fake_api: ContreeAsyncClient, result_image_uuid):
    # `run(tag=...)` calls `tag_as(tag)` on the result once it lands, which is
    # the `update_image_tag` call `queue_tag` mocks.
    queue_run(fake_api, result_image_uuid=str(result_image_uuid))
    queue_tag(fake_api, result_image_uuid, "myapp:ready")
    await tag_on_run_main(fake_api)


def test_tag_on_run_example_s(fake_api_s: ContreeClient, result_image_uuid):
    queue_run(fake_api_s, result_image_uuid=str(result_image_uuid))
    queue_tag(fake_api_s, result_image_uuid, "myapp:ready")
    tag_on_run_main_s(fake_api_s)
