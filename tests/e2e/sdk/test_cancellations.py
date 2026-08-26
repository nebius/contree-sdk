import asyncio
from asyncio import get_event_loop, sleep, wait_for

import pytest
from contree_client.base import ContreeAsyncClient, ContreeSyncClient
from pytest_mock import MockerFixture, MockType

from contree_sdk import Contree, ContreeSync
from contree_sdk.sdk.objects.image import ContreeImage
from tests.utils.interrupter import interrupter


IMPORT_URL = "docker://ghcr.io/linuxserver/code-server:latest"


async def get_operation_id_from_spy(spy_obj: MockType):
    while spy_obj.called is False:
        await sleep(0.01)
    return spy_obj.call_args.args[0]


async def wait_cancel_requested(spy_obj: MockType):
    for _ in range(300):
        if spy_obj.called:
            return
        await sleep(0.01)
    raise AssertionError("cancel_operation was not requested")


async def test_cancel_import(contree: Contree, async_client: ContreeAsyncClient, mocker: MockerFixture):
    spy_wait = mocker.spy(async_client, "wait_operation")
    spy_cancel = mocker.spy(async_client, "cancel_operation")

    task = get_event_loop().create_task(contree.images.oci(IMPORT_URL))
    operation_id = await get_operation_id_from_spy(spy_wait)
    task.cancel()

    await wait_cancel_requested(spy_cancel)
    assert spy_cancel.call_args.args[0] == operation_id


async def test_cancel_import_s(contree_s: ContreeSync, sync_client: ContreeSyncClient, mocker: MockerFixture):
    spy_wait = mocker.spy(sync_client, "wait_operation")
    spy_cancel = mocker.spy(sync_client, "cancel_operation")

    with pytest.raises(KeyboardInterrupt), interrupter(0.5):
        contree_s.images.oci(IMPORT_URL)

    operation_id = spy_wait.call_args.args[0]
    await wait_cancel_requested(spy_cancel)
    assert spy_cancel.call_args.args[0] == operation_id


async def test_timed_out_wait_cancels_operation(
    contree: Contree, image: ContreeImage, async_client: ContreeAsyncClient, mocker: MockerFixture
):
    spy_spawn = mocker.spy(async_client, "spawn_instance")
    spy_cancel = mocker.spy(async_client, "cancel_operation")
    started = await image.run(shell="sleep 60", timeout=60).start()

    with pytest.raises((TimeoutError, asyncio.TimeoutError)):
        await wait_for(started, timeout=2)

    await wait_cancel_requested(spy_cancel)
    assert spy_cancel.call_args.args[0] == spy_spawn.spy_return.uuid
