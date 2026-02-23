from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from contree_sdk import Contree, ContreeSync
from contree_sdk._internals.models.instance import ProcessResources, ProcessState
from contree_sdk.sdk.exceptions import DisposableImageRunError
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.utils.models.operation import OperationStatus
from tests.unit.fixtures.operations import create_operation_model


async def test_use_returns_image_with_none_uuid(fake_contree: Contree):
    image = fake_contree.images.use("my-tag:latest")
    assert isinstance(image, ContreeImage)
    assert image.uuid is None
    assert image.tag == "my-tag:latest"


def test_use_sync_returns_image_with_none_uuid(fake_contree_s: ContreeSync):
    image = fake_contree_s.images.use("my-tag:latest")
    assert isinstance(image, ContreeImageSync)
    assert image.uuid is None
    assert image.tag == "my-tag:latest"


async def test_use_image_run_does_not_raise(fake_contree: Contree):
    image = fake_contree.images.use("my-tag:latest")
    running = image.run(command="echo hello")
    assert running.uuid is None
    assert running.tag == "my-tag:latest"


async def test_use_image_no_tag_raises_disposable_error(fake_contree: Contree):
    image = ContreeImage(client=fake_contree, uuid=None, tag=None)
    with pytest.raises(DisposableImageRunError):
        image.run(command="echo hello")


async def test_use_image_await_passes_tag_spec(
    fake_contree: Contree,
    process_state: ProcessState,
    resource_usage: ProcessResources,
):
    image = fake_contree.images.use("my-tag:latest")
    running = image.run(shell="echo hello")

    result_uuid = uuid4()
    op = create_operation_model(result_uuid, result_uuid, process_state, resource_usage, "", OperationStatus.SUCCESS)

    with (
        patch.object(fake_contree._api, "spawn_instance", new_callable=AsyncMock) as spawn_mock,
        patch.object(fake_contree, "_wait_operation", new_callable=AsyncMock) as wait_mock,
    ):
        spawn_mock.return_value = str(uuid4())
        wait_mock.return_value = (op.metadata, op.result)
        await running

    spawn_mock.assert_called_once()
    assert spawn_mock.call_args[0][0].image == "tag:my-tag:latest"


async def test_use_with_uuid_string(fake_contree: Contree):
    test_uuid = uuid4()
    image = fake_contree.images.use(str(test_uuid))
    assert isinstance(image, ContreeImage)
    assert image.uuid == test_uuid
    assert image.tag is None


async def test_use_with_uuid_object(fake_contree: Contree):
    test_uuid = uuid4()
    image = fake_contree.images.use(test_uuid)
    assert isinstance(image, ContreeImage)
    assert image.uuid == test_uuid
    assert image.tag is None


def test_use_sync_with_uuid_string(fake_contree_s: ContreeSync):
    test_uuid = uuid4()
    image = fake_contree_s.images.use(str(test_uuid))
    assert isinstance(image, ContreeImageSync)
    assert image.uuid == test_uuid
    assert image.tag is None
