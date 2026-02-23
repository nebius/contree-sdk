from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from contree_sdk import Contree, ContreeSync
from contree_sdk._internals.models.instance import (
    InstanceOperationMetadata,
    InstanceOperationResult,
    ProcessExecutionResult,
    ProcessResources,
    ProcessState,
)
from contree_sdk.sdk.exceptions import DisposableImageRunError
from contree_sdk.sdk.objects.image import ContreeImage, ContreeImageSync
from contree_sdk.utils.codecs import io_encode
from contree_sdk.utils.models.stream import StreamDescription, StreamEncoding


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


async def test_use_image_await_passes_tag_spec(fake_contree: Contree):
    image = fake_contree.images.use("my-tag:latest")
    running = image.run(shell="echo hello")

    result_uuid = uuid4()
    process_state = ProcessState(
        continued=False,
        core_dump=False,
        exit_code=0,
        pid=1,
        signal=0,
        stopped=False,
        timed_out=False,
    )
    resources = ProcessResources(
        block_input=0,
        block_output=0,
        cost=0.0,
        elapsed_time=0.5,
        involuntary_switches=0,
        max_rss=1024,
        monotonic_time=0.5,
        page_faults=0,
        page_faults_io=0,
        shared_memory=0,
        signals=0,
        swaps=0,
        system_cpu_time=0.1,
        unshared_memory=0,
        user_cpu_time=0.1,
        voluntary_switches=0,
    )
    metadata = InstanceOperationMetadata(
        args=[],
        command="echo hello",
        cwd="/",
        disposable=True,
        env={},
        files={},
        hostname="hostname",
        image="my-tag:latest",
        shell=True,
        stdin=StreamDescription(value="", encoding=StreamEncoding.ascii),
        timeout=60,
        truncate_output_at=65535,
        result=ProcessExecutionResult(
            stdout=io_encode("", StreamEncoding.base64),
            stderr=io_encode("", StreamEncoding.base64),
            state=process_state,
            resources=resources,
        ),
    )
    op_result = InstanceOperationResult(image=str(result_uuid), tag="result-tag")

    with patch.object(fake_contree._api, "spawn_instance", new_callable=AsyncMock) as spawn_mock:
        spawn_mock.return_value = str(uuid4())

        with patch.object(fake_contree, "_wait_operation", new_callable=AsyncMock) as wait_mock:
            wait_mock.return_value = (metadata, op_result)
            await running

        spawn_mock.assert_called_once()
        request = spawn_mock.call_args[0][0]
        assert request.image == "tag:my-tag:latest"
