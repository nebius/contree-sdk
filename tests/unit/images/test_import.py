from uuid import UUID, uuid4

import pytest
from contree_client.models import OperationResponse, OperationStatus
from contree_client.testing import ContreeAsyncClient, ContreeClient

from contree_sdk import Contree, ContreeSync
from tests.e2e.sdk.images.test_images import test_import_not_real_image as _test_import_not_real_image
from tests.e2e.sdk.images.test_images import test_import_not_real_image_s as _test_import_not_real_image_s
from tests.e2e.sdk.images.test_images import test_import_public_image as _test_import_public_image
from tests.e2e.sdk.images.test_images import test_import_public_image_s as _test_import_public_image_s
from tests.unit.fixtures.imports import queue_import


async def test_import_public_image(fake_contree: Contree, fake_api: ContreeAsyncClient, result_image_uuid: UUID):
    queue_import(fake_api, result_image_uuid=result_image_uuid)
    await _test_import_public_image(fake_contree)


def test_import_public_image_s(fake_contree_s: ContreeSync, fake_api_s: ContreeClient, result_image_uuid: UUID):
    queue_import(fake_api_s, result_image_uuid=result_image_uuid)
    _test_import_public_image_s(fake_contree_s)


async def test_import_with_tag_override(fake_contree: Contree, fake_api: ContreeAsyncClient, result_image_uuid: UUID):
    queue_import(fake_api, result_image_uuid=result_image_uuid)
    image = await fake_contree.images.import_from("docker://ghcr.io/linuxserver/code-server:latest", tag="override")

    assert image.uuid == result_image_uuid
    assert image.tag == "override"

    [call] = fake_api.calls_for("import_image")
    assert call.kwargs["tag"] == "override"


def test_import_with_tag_override_s(fake_contree_s: ContreeSync, fake_api_s: ContreeClient, result_image_uuid: UUID):
    queue_import(fake_api_s, result_image_uuid=result_image_uuid)
    image = fake_contree_s.images.import_from("docker://ghcr.io/linuxserver/code-server:latest", tag="override")

    assert image.uuid == result_image_uuid
    assert image.tag == "override"

    [call] = fake_api_s.calls_for("import_image")
    assert call.kwargs["tag"] == "override"


async def test_pull_import_not_real_image(fake_contree: Contree, fake_api: ContreeAsyncClient):
    queue_import(fake_api, status=OperationStatus.FAILED, error="Import failed")
    await _test_import_not_real_image(fake_contree)


def test_pull_import_not_real_image_s(fake_contree_s: ContreeSync, fake_api_s: ContreeClient):
    queue_import(fake_api_s, status=OperationStatus.FAILED, error="Import failed")
    _test_import_not_real_image_s(fake_contree_s)


async def test_import_by_uuid_raises(fake_contree: Contree):
    with pytest.raises(ValueError, match="Cannot import image by UUID"):
        await fake_contree.images.import_from(str(uuid4()))


def test_import_by_uuid_raises_s(fake_contree_s: ContreeSync):
    with pytest.raises(ValueError, match="Cannot import image by UUID"):
        fake_contree_s.images.import_from(str(uuid4()))


async def test_import_with_username_only_raises(fake_contree: Contree):
    with pytest.raises(ValueError, match="Both username and password must be provided"):
        await fake_contree.images.import_from("docker://ghcr.io/linuxserver/code-server:latest", username="bob")


def test_import_with_username_only_raises_s(fake_contree_s: ContreeSync):
    with pytest.raises(ValueError, match="Both username and password must be provided"):
        fake_contree_s.images.import_from("docker://ghcr.io/linuxserver/code-server:latest", username="bob")


async def test_import_with_credentials_builds_registry(
    fake_contree: Contree, fake_api: ContreeAsyncClient, result_image_uuid: UUID
):
    queue_import(fake_api, result_image_uuid=result_image_uuid)
    await fake_contree.images.import_from(
        "docker://ghcr.io/linuxserver/code-server:latest", username="bob", password="secret"
    )

    [call] = fake_api.calls_for("import_image")
    registry = call.args[0]
    assert registry.credentials.username == "bob"
    assert registry.credentials.password == "secret"


def test_import_with_credentials_builds_registry_s(
    fake_contree_s: ContreeSync, fake_api_s: ContreeClient, result_image_uuid: UUID
):
    queue_import(fake_api_s, result_image_uuid=result_image_uuid)
    fake_contree_s.images.import_from(
        "docker://ghcr.io/linuxserver/code-server:latest", username="bob", password="secret"
    )

    [call] = fake_api_s.calls_for("import_image")
    registry = call.args[0]
    assert registry.credentials.username == "bob"
    assert registry.credentials.password == "secret"


async def test_import_cancelled_raises(fake_contree: Contree, fake_api: ContreeAsyncClient):
    operation_id = str(uuid4())
    fake_api.mock("import_image", operation_id)
    fake_api.mock("wait_operation", OperationResponse(uuid=operation_id, status=OperationStatus.CANCELLED))

    with pytest.raises(InterruptedError, match="was cancelled"):
        await fake_contree.images.import_from("docker://ghcr.io/linuxserver/code-server:latest")


def test_import_cancelled_raises_s(fake_contree_s: ContreeSync, fake_api_s: ContreeClient):
    operation_id = str(uuid4())
    fake_api_s.mock("import_image", operation_id)
    fake_api_s.mock("wait_operation", OperationResponse(uuid=operation_id, status=OperationStatus.CANCELLED))

    with pytest.raises(InterruptedError, match="was cancelled"):
        fake_contree_s.images.import_from("docker://ghcr.io/linuxserver/code-server:latest")


async def test_import_timed_out_raises(fake_contree: Contree, fake_api: ContreeAsyncClient):
    fake_api.mock("import_image", str(uuid4()))
    fake_api.mock("wait_operation", error=TimeoutError("operation did not complete"))
    fake_api.mock("cancel_operation", None)

    with pytest.raises(TimeoutError):
        await fake_contree.images.import_from("docker://ghcr.io/linuxserver/code-server:latest")

    assert fake_api.calls_for("cancel_operation")


def test_import_timed_out_raises_s(fake_contree_s: ContreeSync, fake_api_s: ContreeClient):
    fake_api_s.mock("import_image", str(uuid4()))
    fake_api_s.mock("wait_operation", error=TimeoutError("operation did not complete"))
    fake_api_s.mock("cancel_operation", None)

    with pytest.raises(TimeoutError):
        fake_contree_s.images.import_from("docker://ghcr.io/linuxserver/code-server:latest")

    assert fake_api_s.calls_for("cancel_operation")


async def test_import_without_result_uuid_raises(fake_contree: Contree, fake_api: ContreeAsyncClient):
    queue_import(fake_api, result_image_uuid=None)

    with pytest.raises(RuntimeError, match="no image uuid"):
        await fake_contree.images.import_from("docker://ghcr.io/linuxserver/code-server:latest")


def test_import_without_result_uuid_raises_s(fake_contree_s: ContreeSync, fake_api_s: ContreeClient):
    queue_import(fake_api_s, result_image_uuid=None)

    with pytest.raises(RuntimeError, match="no image uuid"):
        fake_contree_s.images.import_from("docker://ghcr.io/linuxserver/code-server:latest")
