from uuid import UUID, uuid4

import pytest

from contree_sdk import Contree, ContreeSync
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from tests.unit.fixtures.operations import queue_run
from tests.unit.fixtures.runs import RUN_STDERR, RUN_STDOUT


async def test_use_returns_image_with_none_uuid(fake_contree: Contree):
    image = await fake_contree.images.use("my-tag:latest")
    assert isinstance(image, ContreeImage)
    assert image.uuid is None
    assert image.tag == "my-tag:latest"


def test_use_sync_returns_image_with_none_uuid(fake_contree_s: ContreeSync):
    image = fake_contree_s.images.use("my-tag:latest")
    assert isinstance(image, ContreeImageSync)
    assert image.uuid is None
    assert image.tag == "my-tag:latest"


async def test_use_image_run_does_not_raise(fake_contree: Contree):
    image = await fake_contree.images.use("my-tag:latest")
    running = image.run(command="echo hello")
    assert running.uuid is None
    assert running.tag == "my-tag:latest"


async def test_use_image_no_tag_raises_disposable_error(fake_contree: Contree):
    image = ContreeImage(client=fake_contree, uuid=None, tag=None)
    with pytest.raises(RuntimeError):
        image.run(command="echo hello")


async def test_use_image_await_passes_tag_spec(fake_contree: Contree, result_image_uuid: UUID):
    queue_run(fake_contree.api, stdout=RUN_STDOUT, stderr=RUN_STDERR, result_image_uuid=str(result_image_uuid))
    image = await fake_contree.images.use("my-tag:latest")
    await image.run(shell="echo hello")

    [call] = fake_contree.api.calls_for("spawn_instance")
    assert call.args[1] == "tag:my-tag:latest"


async def test_use_with_uuid_string(fake_contree: Contree):
    test_uuid = uuid4()
    image = await fake_contree.images.use(str(test_uuid))
    assert isinstance(image, ContreeImage)
    assert image.uuid == test_uuid
    assert image.tag is None


async def test_use_with_uuid_object(fake_contree: Contree):
    test_uuid = uuid4()
    image = await fake_contree.images.use(test_uuid)
    assert isinstance(image, ContreeImage)
    assert image.uuid == test_uuid
    assert image.tag is None


def test_use_sync_with_uuid_string(fake_contree_s: ContreeSync):
    test_uuid = uuid4()
    image = fake_contree_s.images.use(str(test_uuid))
    assert isinstance(image, ContreeImageSync)
    assert image.uuid == test_uuid
    assert image.tag is None
